from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_media import (
    GPU_MEDIA_SCHEMA,
    GpuMediaCapabilities,
    GpuMediaEvidence,
    GpuMediaKey,
    GpuMediaPolicy,
    GpuMediaTuningStore,
)
from cinepulse.media_profile import ColorProfile


def profile() -> ColorProfile:
    return ColorProfile("bt709", "bt709", "bt709", "tv", "yuv420p", 8, False)


def key() -> GpuMediaKey:
    return GpuMediaKey.from_profile(
        gpu_name="RTX Test",
        driver="999.1",
        ffmpeg_fingerprint="ffmpeg-test",
        codec="h264",
        width=1920,
        height=1080,
        profile=profile(),
        operation="decode",
    )


def capabilities() -> GpuMediaCapabilities:
    return GpuMediaCapabilities(
        ffmpeg="ffmpeg",
        fingerprint="ffmpeg-test",
        hwaccels=frozenset({"cuda"}),
        decoders=frozenset({"h264_cuvid"}),
        filters=frozenset({"scale_cuda"}),
        encoders=frozenset({"h264_nvenc"}),
    )


class H5SeekAlignmentTests(unittest.TestCase):
    def test_failed_seek_alignment_cannot_unlock_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = GpuMediaTuningStore(Path(temporary) / "gpu-media.json")
            evidence = GpuMediaEvidence(
                policy=GpuMediaPolicy("h264_cuvid"),
                baseline_seconds=10.0,
                candidate_seconds=5.0,
                psnr_db=99.0,
                ssim=1.0,
                integrity_ok=True,
                metadata_ok=True,
                frame_count_ok=True,
                audio_sync_ok=True,
                seek_alignment_ok=False,
                seek_psnr_db=20.0,
                seek_ssim=0.5,
            )
            self.assertFalse(store.record(key(), evidence))
            self.assertIsNone(store.lookup(key(), capabilities()))

    def test_seek_approved_record_is_required_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gpu-media.json"
            store = GpuMediaTuningStore(path)
            policy = GpuMediaPolicy("h264_cuvid")
            evidence = GpuMediaEvidence(
                policy=policy,
                baseline_seconds=10.0,
                candidate_seconds=5.0,
                psnr_db=99.0,
                ssim=1.0,
                integrity_ok=True,
                metadata_ok=True,
                frame_count_ok=True,
                audio_sync_ok=True,
                seek_alignment_ok=True,
                seek_psnr_db=99.0,
                seek_ssim=1.0,
            )
            self.assertTrue(store.record(key(), evidence))
            self.assertEqual(policy, store.lookup(key(), capabilities()))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(GPU_MEDIA_SCHEMA, payload["version"])
            record = next(iter(payload["records"].values()))
            self.assertTrue(record["seek_alignment_ok"])
            self.assertEqual(99.0, record["seek_psnr_db"])

    def test_pre_seek_schema_is_invalidated_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gpu-media.json"
            path.write_text(json.dumps({"version": 1, "records": {key().token(): {"accepted": True}}}), encoding="utf-8")
            store = GpuMediaTuningStore(path)
            self.assertIsNone(store.lookup(key(), capabilities()))


if __name__ == "__main__":
    unittest.main()
