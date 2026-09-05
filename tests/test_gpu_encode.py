from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_encode import NvencContract, ResidentEncodeEvidence, ResidentEncodeKey, ResidentEncodeStore


def contract() -> NvencContract:
    return NvencContract(
        encoder="hevc_nvenc", preset="p7", rate_control="vbr", pixel_format="yuv420p", profile="main",
        cq=14, bitrate_kbps=30000, maxrate_kbps=60000, bufsize_kbps=120000, bframes=2,
        tune="hq", spatial_aq=True, temporal_aq=True, aq_strength=8,
        multipass="fullres", b_ref_mode="middle", gop=30,
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
    def test_contract_hash_changes_with_every_quality_relevant_option(self) -> None:
        original = contract()
        variants = [
            NvencContract(**{**original.__dict__, "cq": 15}),
            NvencContract(**{**original.__dict__, "tune": "ll"}),
            NvencContract(**{**original.__dict__, "spatial_aq": False}),
            NvencContract(**{**original.__dict__, "temporal_aq": False}),
            NvencContract(**{**original.__dict__, "aq_strength": 9}),
            NvencContract(**{**original.__dict__, "multipass": "qres"}),
            NvencContract(**{**original.__dict__, "b_ref_mode": "disabled"}),
            NvencContract(**{**original.__dict__, "gop": 60}),
            NvencContract(**{**original.__dict__, "bframes": 3}),
        ]
        self.assertTrue(all(original.token() != item.token() for item in variants))

    def test_ffmpeg_args_keep_complete_cinepulse_quality_contract(self) -> None:
        args = contract().ffmpeg_args()
        joined = " ".join(args)
        for value in (
            "hevc_nvenc", "p7", "-tune hq", "-rc vbr", "-cq 14", "30000k",
            "-spatial-aq 1", "-temporal-aq 1", "-aq-strength 8",
            "-multipass fullres", "-b_ref_mode middle", "-g 30", "-bf 2",
        ):
            self.assertIn(value, joined)

    def test_invalid_aq_strength_without_aq_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            NvencContract("hevc_nvenc", "p7", "vbr", "yuv420p", bitrate_kbps=1000, aq_strength=8)

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
            changed = NvencContract(**{**contract().__dict__, "preset": "p6"})
            self.assertFalse(store.approved(key(changed)))
            self.assertFalse(store.record(key(), changed, good()))


if __name__ == "__main__":
    unittest.main()
