from __future__ import annotations

import unittest

from cinepulse.delivery import DeliveryPlan
from cinepulse.gpu_delivery import cinepulse_hevc_nvenc_contract, select_resident_delivery_route
from cinepulse.gpu_media import GpuMediaCapabilities
from cinepulse.hardware import HardwareProfile
from cinepulse.media_profile import ColorProfile


GPU = HardwareProfile("cpu", 28, "RTX Test", 8192, "999.1")
CAPS = GpuMediaCapabilities(
    ffmpeg="ffmpeg",
    fingerprint="ffmpeg-test",
    cuda=True,
    cuvid=True,
    nvenc=True,
    scale_cuda=True,
    scale_npp=False,
    decoders=frozenset({"h264_cuvid"}),
    encoders=frozenset({"hevc_nvenc"}),
)


class Store:
    def __init__(self, approved: bool) -> None:
        self.value = approved
        self.keys = []

    def approved(self, key) -> bool:
        self.keys.append(key)
        return self.value


def plan() -> DeliveryPlan:
    return DeliveryPlan(
        profile="YouTube / Streaming", container="MP4", suffix=".mp4",
        video_codec="HEVC", audio_codec="AAC", video_encoder="libx265/hevc_nvenc",
        audio_encoder="aac", pixel_format="yuv420p", bit_depth=8, hdr=False,
        lossless_video=False, lossless_audio=False,
    )


def profile() -> ColorProfile:
    return ColorProfile("yuv420p", 8, "bt709", "bt709", "bt709", "tv", False)


def select(*, store=None, source_fps=60.0, target_fps=60, target=(3840, 2160), source=(1920, 1080), color_final=True):
    return select_resident_delivery_route(
        hardware=GPU,
        caps=CAPS,
        store=store or Store(False),
        source_stream={"codec_name": "h264", "width": source[0], "height": source[1]},
        source_profile=profile(),
        source_fps=source_fps,
        target_width=target[0], target_height=target[1], target_fps=target_fps,
        delivery_plan=plan(), bitrate_mbps=80, use_cpu=False,
        color_already_final=color_final,
    )


class GpuDeliveryTests(unittest.TestCase):
    def test_contract_args_are_identical_to_delivery_plan_hevc_nvenc(self) -> None:
        expected = plan().video_args(use_cpu=False, nvenc_available=True, bitrate_mbps=80, fps=60)
        actual = cinepulse_hevc_nvenc_contract(pixel_format="yuv420p", bitrate_mbps=80, fps=60).ffmpeg_args()
        self.assertEqual(expected, actual)

    def test_exact_evidence_allows_simple_same_aspect_resident_route(self) -> None:
        store = Store(True)
        route = select(store=store)
        self.assertTrue(route.approved)
        self.assertEqual("h264_cuvid", route.decoder)
        self.assertEqual("scale_cuda", route.scaler)
        self.assertEqual(1, len(store.keys))
        self.assertEqual(route.contract.token(), store.keys[0].encode_contract)

    def test_missing_evidence_stays_cpu(self) -> None:
        route = select(store=Store(False))
        self.assertFalse(route.approved)
        self.assertIsNotNone(route.key)

    def test_temporal_filter_requirement_stays_cpu_without_querying_store(self) -> None:
        store = Store(True)
        route = select(store=store, source_fps=30.0, target_fps=60)
        self.assertFalse(route.approved)
        self.assertEqual([], store.keys)

    def test_crop_pad_requirement_stays_cpu(self) -> None:
        route = select(store=Store(True), target=(3840, 1600))
        self.assertFalse(route.approved)
        self.assertIn("crop/pad", route.reason)

    def test_unfinished_color_contract_stays_cpu(self) -> None:
        route = select(store=Store(True), color_final=False)
        self.assertFalse(route.approved)
        self.assertIn("color/HDR", route.reason)


if __name__ == "__main__":
    unittest.main()
