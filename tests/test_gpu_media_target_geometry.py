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
)
from cinepulse.media_profile import ColorProfile


PROFILE = ColorProfile("bt709", "bt709", "bt709", "tv", "yuv420p", 8, False)
CAPS = GpuMediaCapabilities(
    ffmpeg="ffmpeg",
    fingerprint="build-a",
    hwaccels=frozenset({"cuda"}),
    decoders=frozenset({"h264_cuvid"}),
    filters=frozenset({"scale_cuda"}),
    encoders=frozenset({"h264_nvenc"}),
)


def scale_key(target_width: int, target_height: int) -> GpuMediaKey:
    return GpuMediaKey.from_profile(
        gpu_name="RTX Test",
        driver="999.1",
        ffmpeg_fingerprint="build-a",
        codec="h264",
        width=1920,
        height=1080,
        target_width=target_width,
        target_height=target_height,
        profile=PROFILE,
        operation="decode-scale",
    )


class GpuMediaTargetGeometryTests(unittest.TestCase):
    def test_target_geometry_changes_exact_cache_key(self) -> None:
        self.assertNotEqual(scale_key(3840, 2160).token(), scale_key(7680, 4320).token())

    def test_4k_evidence_cannot_unlock_8k_scale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuMediaTuningStore(Path(temporary) / "gpu-media.json")
            policy = GpuMediaPolicy("h264_cuvid", scaler="scale_cuda")
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
            self.assertTrue(store.record(scale_key(3840, 2160), evidence))
            self.assertEqual(policy, store.lookup(scale_key(3840, 2160), CAPS))
            self.assertIsNone(store.lookup(scale_key(7680, 4320), CAPS))


if __name__ == "__main__":
    unittest.main()
