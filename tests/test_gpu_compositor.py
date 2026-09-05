from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorEvidence,
    GpuCompositorKey,
    GpuCompositorStore,
    OverlayLayer,
    build_cuda_overlay_filter,
    cuda_layer_eligible,
    overlay_cuda_position,
)


def caps() -> GpuCompositorCapabilities:
    return GpuCompositorCapabilities("ffmpeg", "ffmpeg-test", True, True, True, True)


def key(layer: OverlayLayer) -> GpuCompositorKey:
    return GpuCompositorKey(
        gpu_name="RTX Test",
        driver="999.1",
        ffmpeg_fingerprint="ffmpeg-test",
        width=3840,
        height=2160,
        fps_milli=60000,
        pixel_format="yuv420p",
        primaries="bt709",
        transfer="bt709",
        space="bt709",
        color_range="tv",
        layer_contract=layer.contract_token(),
    )


class GpuCompositorTests(unittest.TestCase):
    def test_layer_contract_exposes_requested_preview_controls(self) -> None:
        layer = OverlayLayer(
            "logo.png", "png", x=0.25, y=0.75, opacity=0.8, z_order=2,
            rotation_degrees=0.0, loop=True, spin_rpm=0.0, pulse=0.0,
            beat_reaction=0.0, audio_binding="vocals",
        )
        self.assertEqual("vocals", layer.audio_binding)
        self.assertEqual(2, layer.z_order)
        self.assertTrue(layer.contract_token())

    def test_initial_cuda_envelope_rejects_unproven_scale_rotation_and_reactivity(self) -> None:
        self.assertTrue(cuda_layer_eligible(OverlayLayer("a.png", "png"), caps()))
        self.assertFalse(cuda_layer_eligible(OverlayLayer("a.png", "png", scale=1.25), caps()))
        self.assertFalse(cuda_layer_eligible(OverlayLayer("a.png", "png", rotation_degrees=5), caps()))
        self.assertFalse(cuda_layer_eligible(OverlayLayer("a.png", "png", beat_reaction=1), caps()))

    def test_filter_uses_supported_yuv420_alpha_formats_and_downloads_result(self) -> None:
        graph = build_cuda_overlay_filter(
            OverlayLayer("a.png", "png", x=0.25, y=0.75, opacity=0.5),
            canvas_width=1920,
            canvas_height=1080,
            layer_width=256,
            layer_height=256,
        )
        self.assertIn("format=yuv420p,hwupload_cuda", graph)
        self.assertIn("format=yuva420p", graph)
        self.assertIn("overlay_cuda", graph)
        self.assertIn("hwdownload,format=yuv420p", graph)
        self.assertIn("colorchannelmixer=aa=0.50000000", graph)

    def test_position_is_normalized_center_space(self) -> None:
        x, y = overlay_cuda_position(OverlayLayer("a.png", "png", x=0.25, y=0.75), 1920, 1080)
        self.assertIn("0.25000000", x)
        self.assertIn("0.75000000", y)

    def test_evidence_must_be_near_identical_and_faster(self) -> None:
        good = GpuCompositorEvidence(10.0, 6.0, 90.0, 1.0, True, True, True, True)
        visible_change = GpuCompositorEvidence(10.0, 6.0, 50.0, 0.999, True, True, True, True)
        slower = GpuCompositorEvidence(10.0, 10.0, 90.0, 1.0, True, True, True, True)
        self.assertTrue(good.accepted)
        self.assertFalse(visible_change.accepted)
        self.assertFalse(slower.accepted)

    def test_runtime_permission_is_exact_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuCompositorStore(Path(temporary) / "compositor.json")
            layer = OverlayLayer("logo.png", "png")
            evidence = GpuCompositorEvidence(10.0, 6.0, 90.0, 1.0, True, True, True, True)
            self.assertFalse(store.approved(key(layer), caps()))
            self.assertTrue(store.record(key(layer), evidence))
            self.assertTrue(store.approved(key(layer), caps()))
            no_cuda = GpuCompositorCapabilities("ffmpeg", "ffmpeg-test", False, True, True, True)
            self.assertFalse(store.approved(key(layer), no_cuda))
            changed = OverlayLayer("logo.png", "png", opacity=0.8)
            self.assertFalse(store.approved(key(changed), caps()))


if __name__ == "__main__":
    unittest.main()
