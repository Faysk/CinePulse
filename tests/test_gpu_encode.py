from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_encode import NvencContract, ResidentEncodeEvidence, ResidentEncodeKey, ResidentEncodeStore


def contract() -> NvencContract:
    return NvencContract(
        encoder="h264_nvenc", preset="p7", rate_control="vbr", pixel_format="yuv420p",
        cq=18, bitrate_kbps=30000, maxrate_kbps=45000, bufsize_kbps=90000, lookahead=16, bframes=3,
    )


def key(value: NvencContract | None = None) -> ResidentEncodeKey:
    value = value or contract()
    return ResidentEncodeKey(
        gpu_name="RTX Test", driver="999.1", ffmpeg_fingerprint="ffmpeg-test", source_codec="h264",
        source_width=1920, source_height=1080, target_width=3840, target_height=2160,
        source_pixel_format="yuv420p", primaries="bt709", transfer="bt709", space="bt709", color_range="tv",
        scaler="scale_cuda", encode_contract=value.token(),
    )


def good() -> ResidentEncodeEvidence:
    return ResidentEncodeEvidence(10.0, 6.0, 70.0, 0.9999, True, True, True, True, True, 1000, 1000)


class GpuEncodeTests(unittest.TestCase):
    def test_contract_hash_changes_with_quality_options(self) -> None:
        original = contract()
        changed = NvencContract(
            encoder="h264_nvenc", preset="p7", rate_control="vbr", pixel_format="yuv420p",
            cq=20, bitrate_kbps=30000, maxrate_kbps=45000, bufsize_kbps=90000, lookahead=16, bframes=3,
        )
        self.assertNotEqual(original.token(), changed.token())

    def test_ffmpeg_args_keep_explicit_rate_control(self) -> None:
        args = contract().ffmpeg_args()
        self.assertIn("h264_nvenc", args)
        self.assertIn("p7", args)
        self.assertIn("-cq", args)
        self.assertIn("30000k", args)
        self.assertIn("-rc-lookahead", args)

    def test_quality_or_seek_regression_is_rejected(self) -> None:
        quality_bad = ResidentEncodeEvidence(10, 5, 40, 0.99, True, True, True, True, True, 100, 100)
        seek_bad = ResidentEncodeEvidence(10, 5, 70, 1.0, True, True, True, False, True, 100, 100)
        self.assertFalse(quality_bad.accepted)
        self.assertFalse(seek_bad.accepted)

    def test_slow_resident_path_is_not_approved(self) -> None:
        slow = ResidentEncodeEvidence(10, 10, 70, 1.0, True, True, True, True, True, 100, 100)
        self.assertFalse(slow.accepted)

    def test_store_requires_exact_encoder_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ResidentEncodeStore(Path(temporary) / "resident.json")
            self.assertTrue(store.record(key(), contract(), good()))
            self.assertTrue(store.approved(key()))
            changed = NvencContract(
                encoder="h264_nvenc", preset="p6", rate_control="vbr", pixel_format="yuv420p",
                cq=18, bitrate_kbps=30000, maxrate_kbps=45000, bufsize_kbps=90000, lookahead=16, bframes=3,
            )
            self.assertFalse(store.approved(key(changed)))
            self.assertFalse(store.record(key(), changed, good()))


if __name__ == "__main__":
    unittest.main()
