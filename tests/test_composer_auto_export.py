from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from cinepulse.composer_auto_export import _export_gpu, _gpu_visual_command, export_composer_auto
from cinepulse.composer_export import ComposerExportRequest, ComposerExportResult
from cinepulse.composer_gpu_route import ComposerGpuRoute
from cinepulse.composer_profile import ComposerBaseProfile
from cinepulse.gpu_compositor import GpuCompositorCapabilities, GpuCompositorKey, OverlayLayer
from cinepulse.hardware import HardwareProfile
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState


GPU = HardwareProfile("cpu", 16, "RTX Test", 8192, "999.1")
CAPS = GpuCompositorCapabilities("ffmpeg", "ffmpeg-test", True, True, True, True)


class Store:
    def __init__(self) -> None:
        self.invalidated = []

    def approved(self, key, caps) -> bool:
        return True

    def invalidate(self, key) -> bool:
        self.invalidated.append(key)
        return True

    def benchmark_due(self, key, *, cooldown_seconds=21600.0) -> bool:
        return True

    def record_rejection(self, key, evidence) -> None:
        return None


def make_request(root: Path) -> ComposerExportRequest:
    source = root / "base.mp4"
    source.write_bytes(b"source")
    layer = OverlayLayer(str(root / "logo.png"), "png")
    state = OverlayComposerState([ComposerItem("logo", media=layer)])
    return ComposerExportRequest(
        source=source,
        output=root / "out.mkv",
        profile=ComposerBaseProfile(64, 36, 24.0, 1.0, "yuv420p", "bt709", "bt709", "bt709", "tv"),
        state=state,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        audio_sources={},
    )


def route(request: ComposerExportRequest, *, use_gpu: bool) -> ComposerGpuRoute:
    layer = request.state.ordered()[0].media
    assert layer is not None
    key = GpuCompositorKey("RTX Test", "999.1", "ffmpeg-test", 64, 36, 24000, "yuv420p", "bt709", "bt709", "bt709", "tv", "stack")
    return ComposerGpuRoute(use_gpu, "test", layer, key, (layer,))


class ComposerAutoExportTests(unittest.TestCase):
    def test_nvdec_resident_command_keeps_base_on_cuda(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            selected = route(request, use_gpu=True)
            assert selected.key is not None
            selected = replace(
                selected,
                key=replace(selected.key, gpu_index=1),
                base_decoder="h264_cuvid",
            )
            command = _gpu_visual_command(request, selected, Path(temp) / "visual.mkv")
            self.assertIn("-init_hw_device", command)
            self.assertIn("cuda=cinepulse_gpu:1", command)
            self.assertIn("-filter_hw_device", command)
            self.assertEqual("cinepulse_gpu", command[command.index("-filter_hw_device") + 1])
            self.assertIn("-hwaccel", command)
            self.assertEqual("1", command[command.index("-hwaccel_device") + 1])
            self.assertIn("-hwaccel_output_format", command)
            self.assertIn("h264_cuvid", command)
            graph = command[command.index("-filter_complex") + 1]
            self.assertIn("[0:v][layergpu1]overlay_cuda", graph)
            self.assertNotIn("[0:v]format=yuv420p,hwupload_cuda[basegpu]", graph)

    def test_gpu_visual_master_is_frame_bound_without_duration_clip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            selected = route(request, use_gpu=True)
            command = _gpu_visual_command(request, selected, Path(temp) / "visual.mkv")
            self.assertIn("-frames:v", command)
            self.assertEqual("24", command[command.index("-frames:v") + 1])
            self.assertNotIn("-t", command)

    def test_still_background_stays_cpu_without_gpu_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            request = replace(request, profile=replace(request.profile, still_image=True))
            with (
                patch("cinepulse.composer_auto_export._export_gpu") as gpu,
                patch("cinepulse.composer_auto_export.export_composer_reference", return_value=ComposerExportResult(request.output, 24)) as cpu,
            ):
                result = export_composer_auto(request, hardware=GPU, capabilities=CAPS, store=Store())
            self.assertEqual("cpu-reference", result.backend)
            self.assertFalse(result.gpu_attempted)
            gpu.assert_not_called()
            cpu.assert_called_once()

    def test_unapproved_route_uses_cpu_without_gpu_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            with (
                patch("cinepulse.composer_auto_export.select_gpu_export_route", return_value=route(request, use_gpu=False)),
                patch("cinepulse.composer_auto_export._export_gpu") as gpu,
                patch("cinepulse.composer_auto_export.export_composer_reference", return_value=ComposerExportResult(request.output, 24)) as cpu,
            ):
                result = export_composer_auto(request, hardware=GPU, capabilities=CAPS, store=Store())
            self.assertEqual("cpu-reference", result.backend)
            self.assertFalse(result.gpu_attempted)
            gpu.assert_not_called()
            cpu.assert_called_once()

    def test_missing_exact_evidence_can_be_learned_then_promoted_to_gpu(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            missing = route(request, use_gpu=False)
            missing = ComposerGpuRoute(
                False,
                "exact H6 GPU/driver/FFmpeg/profile/ordered-stack evidence is absent or stale",
                missing.layer,
                missing.key,
                missing.layers,
            )
            with (
                patch("cinepulse.composer_auto_export.select_gpu_export_route", return_value=missing),
                patch("cinepulse.composer_auto_export._learn_exact_gpu_route", return_value=True) as learn,
                patch(
                    "cinepulse.composer_auto_export._export_gpu",
                    return_value=ComposerExportResult(request.output, 24),
                ) as gpu,
                patch("cinepulse.composer_auto_export.export_composer_reference") as cpu,
            ):
                result = export_composer_auto(
                    request, hardware=GPU, capabilities=CAPS, store=Store()
                )
            self.assertEqual("cuda", result.backend)
            self.assertTrue(result.gpu_attempted)
            learn.assert_called_once()
            gpu.assert_called_once()
            cpu.assert_not_called()

    def test_rejected_on_demand_learning_keeps_cpu_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            missing = route(request, use_gpu=False)
            missing = ComposerGpuRoute(
                False,
                "exact H6 GPU/driver/FFmpeg/profile/ordered-stack evidence is absent or stale",
                missing.layer,
                missing.key,
                missing.layers,
            )
            with (
                patch("cinepulse.composer_auto_export.select_gpu_export_route", return_value=missing),
                patch("cinepulse.composer_auto_export._learn_exact_gpu_route", return_value=False) as learn,
                patch("cinepulse.composer_auto_export._export_gpu") as gpu,
                patch(
                    "cinepulse.composer_auto_export.export_composer_reference",
                    return_value=ComposerExportResult(request.output, 24),
                ) as cpu,
            ):
                result = export_composer_auto(
                    request, hardware=GPU, capabilities=CAPS, store=Store()
                )
            self.assertEqual("cpu-reference", result.backend)
            self.assertFalse(result.gpu_attempted)
            learn.assert_called_once()
            gpu.assert_not_called()
            cpu.assert_called_once()

    def test_approved_route_uses_gpu_and_does_not_touch_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            with (
                patch("cinepulse.composer_auto_export.select_gpu_export_route", return_value=route(request, use_gpu=True)),
                patch("cinepulse.composer_auto_export._export_gpu", return_value=ComposerExportResult(request.output, 24)) as gpu,
                patch("cinepulse.composer_auto_export.export_composer_reference") as cpu,
            ):
                result = export_composer_auto(request, hardware=GPU, capabilities=CAPS, store=Store())
            self.assertEqual("cuda", result.backend)
            self.assertTrue(result.gpu_attempted)
            gpu.assert_called_once()
            cpu.assert_not_called()

    def test_gpu_oom_preserves_evidence_and_retries_cpu_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            store = Store()
            selected = route(request, use_gpu=True)
            with (
                patch("cinepulse.composer_auto_export.select_gpu_export_route", return_value=selected),
                patch(
                    "cinepulse.composer_auto_export._export_gpu",
                    side_effect=RuntimeError("CUDA out of memory"),
                ) as gpu,
                patch(
                    "cinepulse.composer_auto_export.export_composer_reference",
                    return_value=ComposerExportResult(request.output, 24),
                ) as cpu,
            ):
                result = export_composer_auto(
                    request, hardware=GPU, capabilities=CAPS, store=store
                )
            self.assertEqual("cpu-reference", result.backend)
            self.assertTrue(result.gpu_attempted)
            self.assertIn("out of memory", (result.gpu_failure or "").lower())
            self.assertEqual([], store.invalidated)
            gpu.assert_called_once()
            cpu.assert_called_once()

    def test_gpu_failure_invalidates_exact_key_and_retries_cpu_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            store = Store()
            selected = route(request, use_gpu=True)
            with (
                patch("cinepulse.composer_auto_export.select_gpu_export_route", return_value=selected),
                patch("cinepulse.composer_auto_export._export_gpu", side_effect=RuntimeError("cuda exploded")),
                patch("cinepulse.composer_auto_export.export_composer_reference", return_value=ComposerExportResult(request.output, 24)) as cpu,
            ):
                result = export_composer_auto(request, hardware=GPU, capabilities=CAPS, store=store)
            self.assertEqual("cpu-reference", result.backend)
            self.assertTrue(result.gpu_attempted)
            self.assertIn("cuda exploded", result.gpu_failure or "")
            self.assertEqual([selected.key], store.invalidated)
            cpu.assert_called_once()

    def test_gpu_cancellation_never_invalidates_or_retries_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            request = make_request(Path(temp))
            store = Store()
            with (
                patch("cinepulse.composer_auto_export.select_gpu_export_route", return_value=route(request, use_gpu=True)),
                patch("cinepulse.composer_auto_export._export_gpu", side_effect=InterruptedError("cancelled")),
                patch("cinepulse.composer_auto_export.export_composer_reference") as cpu,
            ):
                with self.assertRaises(InterruptedError):
                    export_composer_auto(request, hardware=GPU, capabilities=CAPS, store=store)
            self.assertEqual([], store.invalidated)
            cpu.assert_not_called()

    def test_gpu_export_promotes_through_atomic_factory_and_cleans_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = make_request(root)
            selected = route(request, use_gpu=True)

            def fake_run(command, **_kwargs):
                Path(command[-1]).write_bytes(b"validated-product")

            with (
                patch("cinepulse.composer_auto_export._run_cancellable", side_effect=fake_run),
                patch("cinepulse.composer_auto_export._verify_gpu_product"),
                patch("cinepulse.composer_auto_export._has_audio_stream", return_value=False),
            ):
                result = _export_gpu(
                    request,
                    selected,
                    cancelled=lambda: False,
                    log=lambda _message: None,
                )

            self.assertEqual(request.output, result.output)
            self.assertEqual(b"validated-product", request.output.read_bytes())
            self.assertEqual([], list(root.glob(".*.partial-*")))


if __name__ == "__main__":
    unittest.main()
