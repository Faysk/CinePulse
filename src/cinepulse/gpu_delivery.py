from __future__ import annotations

"""Pure H5 planner for an exact CUDA-resident final-delivery fast path.

The planner is intentionally narrower than normal CinePulse delivery. It may
replace the CPU/zscale feed only when the existing final filter is equivalent to
plain same-aspect scaling (or no scaling), cadence and SDR BT.709 are already
final, the selected codec is HEVC/NVENC, and the exact resident evidence record
exists. Everything else stays on the established CPU/color-critical graph.
"""

from dataclasses import dataclass
from typing import Mapping

from .delivery import DeliveryPlan
from .gpu_encode import NvencContract, ResidentEncodeKey, ResidentEncodeStore
from .gpu_media import GpuMediaCapabilities
from .hardware import HardwareProfile
from .media_profile import ColorProfile


@dataclass(frozen=True)
class ResidentDeliveryRoute:
    approved: bool
    reason: str
    key: ResidentEncodeKey | None = None
    contract: NvencContract | None = None
    decoder: str | None = None
    scaler: str | None = None
    gpu_index: int = 0

    def input_args(self) -> list[str]:
        if not self.approved or not self.decoder:
            return []
        return [
            "-hwaccel", "cuda", "-hwaccel_device", str(self.gpu_index),
            "-hwaccel_output_format", "cuda", "-c:v", self.decoder,
        ]

    def video_filter(self, width: int, height: int) -> str | None:
        if not self.approved or not self.scaler:
            return None
        assert self.contract is not None
        return f"{self.scaler}=w={max(1, int(width))}:h={max(1, int(height))}:format={self.contract.pixel_format}"


def cinepulse_hevc_nvenc_contract(*, pixel_format: str, bitrate_mbps: int, fps: int) -> NvencContract:
    """Mirror DeliveryPlan.video_args HEVC/NVENC without lossy translation."""
    target = max(4, int(bitrate_mbps))
    cadence = max(1, int(fps))
    return NvencContract(
        encoder="hevc_nvenc",
        preset="p7",
        tune="hq",
        rate_control="vbr",
        pixel_format=str(pixel_format),
        profile="main10" if "10" in str(pixel_format) or str(pixel_format).lower().startswith("p010") else "main",
        cq=14,
        bitrate_kbps=target * 1000,
        maxrate_kbps=target * 2000,
        bufsize_kbps=target * 4000,
        spatial_aq=True,
        temporal_aq=True,
        aq_strength=8,
        multipass="fullres",
        b_ref_mode="middle",
        gop=max(12, cadence // 2),
        bframes=2,
    )


def _known_sdr_bt709(profile: ColorProfile) -> bool:
    return bool(
        not profile.hdr
        and profile.bit_depth <= 8
        and profile.primaries == "bt709"
        and profile.transfer in {"bt709", "iec61966-2-1"}
        and profile.space == "bt709"
        and profile.range not in {"", "unknown", "unspecified", "reserved"}
    )


def _same_aspect(source_w: int, source_h: int, target_w: int, target_h: int) -> bool:
    if min(source_w, source_h, target_w, target_h) <= 0:
        return False
    left = source_w / source_h
    right = target_w / target_h
    return abs(left - right) <= 1e-6


def select_resident_delivery_route(
    *,
    hardware: HardwareProfile,
    caps: GpuMediaCapabilities,
    store: ResidentEncodeStore,
    source_stream: Mapping[str, object],
    source_profile: ColorProfile,
    source_fps: float,
    target_width: int,
    target_height: int,
    target_fps: int,
    delivery_plan: DeliveryPlan,
    bitrate_mbps: int,
    use_cpu: bool,
    color_already_final: bool,
    gpu_index: int = 0,
) -> ResidentDeliveryRoute:
    if use_cpu:
        return ResidentDeliveryRoute(False, "CPU delivery was explicitly requested")
    if delivery_plan.video_codec != "HEVC":
        return ResidentDeliveryRoute(False, "resident H5 route currently proves HEVC/NVENC only")
    if not hardware.gpu:
        return ResidentDeliveryRoute(False, "no NVIDIA GPU detected")
    if not color_already_final or not _known_sdr_bt709(source_profile):
        return ResidentDeliveryRoute(False, "color/HDR conversion is not equivalent to the resident CUDA envelope")
    if abs(float(source_fps) - float(target_fps)) > 0.01:
        return ResidentDeliveryRoute(False, "temporal filtering would be required")
    source_w = int(source_stream.get("width") or 0)
    source_h = int(source_stream.get("height") or 0)
    if not _same_aspect(source_w, source_h, target_width, target_height):
        return ResidentDeliveryRoute(False, "crop/pad framing would be required")
    codec = str(source_stream.get("codec_name") or "").lower()
    decoder = caps.decoder_for(codec)
    if not decoder or "hevc_nvenc" not in caps.encoders:
        return ResidentDeliveryRoute(False, "exact NVDEC/NVENC capabilities are unavailable")
    do_scale = (source_w, source_h) != (int(target_width), int(target_height))
    scaler = caps.cuda_scale if do_scale else None
    if do_scale and not scaler:
        return ResidentDeliveryRoute(False, "CUDA scaler unavailable for requested geometry")

    contract = cinepulse_hevc_nvenc_contract(
        pixel_format=delivery_plan.pixel_format,
        bitrate_mbps=bitrate_mbps,
        fps=target_fps,
    )
    key = ResidentEncodeKey(
        gpu_name=hardware.gpu,
        driver=hardware.driver or "unknown-driver",
        ffmpeg_fingerprint=caps.fingerprint,
        source_codec=codec,
        source_width=source_w,
        source_height=source_h,
        target_width=max(1, int(target_width)),
        target_height=max(1, int(target_height)),
        source_pixel_format=source_profile.pixel_format,
        primaries=source_profile.primaries,
        transfer=source_profile.transfer,
        space=source_profile.space,
        color_range=source_profile.range,
        scaler=scaler or "none",
        encode_contract=contract.token(),
    )
    if not store.approved(key):
        return ResidentDeliveryRoute(False, "exact resident decode/scale/encode evidence is absent or stale", key, contract, decoder, scaler, gpu_index)
    return ResidentDeliveryRoute(True, "exact H5 resident evidence approved", key, contract, decoder, scaler, gpu_index)
