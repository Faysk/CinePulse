from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_media import (
    GpuMediaCapabilities,
    GpuMediaEvidence,
    GpuMediaKey,
    GpuMediaPolicy,
    GpuMediaTuningStore,
    safe_candidate_policies,
    select_proven_policy,
)
from cinepulse.media_profile import ColorProfile


def capabilities(*, scaler: bool = True) -> GpuMediaCapabilities:
    filters = {"scale_cuda"} if scaler else set()
    return GpuMediaCapabilities(
        ffmpeg="ffmpeg",
        fingerprint="ffmpeg-test",
        hwaccels=frozenset({"cuda"}),
        decoders=frozenset({"h264_cuvid", "hevc_cuvid"}),
        filters=frozenset(filters),
        encoders=frozenset({"h264_nvenc", "hevc_nvenc"}),
    )


def sdr_profile() -> ColorProfile:
    return ColorProfile("bt709", "bt709", "bt709", "tv", "yuv420p", 8, False)


def key(profile: ColorProfile | None = None, operation: str = "decode") -> GpuMediaKey:
    return GpuMediaKey.from_profile(
        gpu_name="RTX Test",
        driver="999.1",
        ffmpeg_fingerprint="ffmpeg-test",
        codec="h264",
        width=1920,
        height=1080,
        profile=profile or sdr_profile(),
        operation=operation,
    )


class GpuMediaTests(unittest.TestCase):
    def test_sdr_known_color_can_generate_benchmark_candidate(self) -> None:
        values = safe_candidate_policies(capabilities(), codec="h264", profile=sdr_profile())
        self.assertEqual(1, len(values))
        self.assertEqual("h264_cuvid", values[0].decoder)
        self.assertIsNone(values[0].scaler)

    def test_scaler_is_candidate_only_when_explicitly_requested(self) -> None:
        values = safe_candidate_policies(
            capabilities(), codec="h264", profile=sdr_profile(), allow_scale=True, encoder="h264_nvenc"
        )
        self.assertEqual(2, len(values))
        self.assertEqual("scale_cuda", values[1].scaler)
        self.assertEqual("h264_nvenc", values[1].encoder)

    def test_hdr_never_generates_candidate_in_initial_h5_envelope(self) -> None:
        hdr = ColorProfile("bt2020", "smpte2084", "bt2020nc", "tv", "yuv420p10le", 10, True)
        self.assertEqual((), safe_candidate_policies(capabilities(), codec="hevc", profile=hdr, allow_scale=True))

    def test_unknown_color_never_generates_candidate(self) -> None:
        unknown = ColorProfile("unknown", "bt709", "bt709", "tv", "yuv420p", 8, False)
        self.assertEqual((), safe_candidate_policies(capabilities(), codec="h264", profile=unknown))

    def test_unproven_gpu_path_fails_closed_to_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuMediaTuningStore(Path(temporary) / "gpu-media.json")
            self.assertIsNone(
                select_proven_policy(
                    store=store, key=key(), capabilities=capabilities(), profile=sdr_profile()
                )
            )

    def test_quality_or_metadata_failure_cannot_be_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuMediaTuningStore(Path(temporary) / "gpu-media.json")
            policy = GpuMediaPolicy("h264_cuvid")
            bad_quality = GpuMediaEvidence(
                policy=policy,
                baseline_seconds=10.0,
                candidate_seconds=5.0,
                psnr_db=49.0,
                ssim=0.9999,
                integrity_ok=True,
                metadata_ok=True,
                frame_count_ok=True,
                audio_sync_ok=True,
            )
            self.assertFalse(store.record(key(), bad_quality))
            bad_metadata = GpuMediaEvidence(
                policy=policy,
                baseline_seconds=10.0,
                candidate_seconds=5.0,
                psnr_db=80.0,
                ssim=1.0,
                integrity_ok=True,
                metadata_ok=False,
                frame_count_ok=True,
                audio_sync_ok=True,
            )
            self.assertFalse(store.record(key(), bad_metadata))
            self.assertIsNone(store.lookup(key(), capabilities()))

    def test_exact_approved_evidence_unlocks_only_matching_capability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuMediaTuningStore(Path(temporary) / "gpu-media.json")
            policy = GpuMediaPolicy("h264_cuvid")
            evidence = GpuMediaEvidence(
                policy=policy,
                baseline_seconds=10.0,
                candidate_seconds=6.0,
                psnr_db=70.0,
                ssim=0.99999,
                integrity_ok=True,
                metadata_ok=True,
                frame_count_ok=True,
                audio_sync_ok=True,
            )
            self.assertTrue(store.record(key(), evidence))
            self.assertEqual(policy, store.lookup(key(), capabilities()))
            missing_decoder = GpuMediaCapabilities(
                ffmpeg="ffmpeg",
                fingerprint="ffmpeg-test",
                hwaccels=frozenset({"cuda"}),
                decoders=frozenset(),
                filters=frozenset({"scale_cuda"}),
                encoders=frozenset({"h264_nvenc"}),
            )
            self.assertIsNone(store.lookup(key(), missing_decoder))

    def test_evidence_is_exact_for_driver_and_color_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuMediaTuningStore(Path(temporary) / "gpu-media.json")
            policy = GpuMediaPolicy("h264_cuvid")
            evidence = GpuMediaEvidence(
                policy=policy,
                baseline_seconds=10.0,
                candidate_seconds=6.0,
                psnr_db=70.0,
                ssim=1.0,
                integrity_ok=True,
                metadata_ok=True,
                frame_count_ok=True,
                audio_sync_ok=True,
            )
            self.assertTrue(store.record(key(), evidence))
            different_driver = GpuMediaKey.from_profile(
                gpu_name="RTX Test",
                driver="999.2",
                ffmpeg_fingerprint="ffmpeg-test",
                codec="h264",
                width=1920,
                height=1080,
                profile=sdr_profile(),
                operation="decode",
            )
            self.assertIsNone(store.lookup(different_driver, capabilities()))

    def test_runtime_policy_failure_can_be_invalidated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuMediaTuningStore(Path(temporary) / "gpu-media.json")
            policy = GpuMediaPolicy("h264_cuvid")
            evidence = GpuMediaEvidence(
                policy=policy,
                baseline_seconds=10.0,
                candidate_seconds=6.0,
                psnr_db=70.0,
                ssim=1.0,
                integrity_ok=True,
                metadata_ok=True,
                frame_count_ok=True,
                audio_sync_ok=True,
            )
            self.assertTrue(store.record(key(), evidence))
            self.assertTrue(store.invalidate(key()))
            self.assertIsNone(store.lookup(key(), capabilities()))


if __name__ == "__main__":
    unittest.main()
