from __future__ import annotations

"""Evidence-gated H6 route selection for Preview Composer exports.

This module intentionally decides *permission* only.  Capability detection is
not enough: the exact GPU/driver/FFmpeg/base-profile/layer contract must have a
record produced by the physical H6 benchmark.  Projects outside the narrow
single static-media envelope remain on the deterministic CPU reference.
"""

from dataclasses import dataclass
from pathlib import Path

from .gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorKey,
    GpuCompositorStore,
    OverlayLayer,
    cuda_layer_eligible,
)
from .hardware import HardwareInfo
from .overlay_composer import OverlayComposerState


@dataclass(frozen=True)
class ComposerGpuRoute:
    use_gpu: bool
    reason: str
    layer: OverlayLayer | None = None
    key: GpuCompositorKey | None = None


def build_compositor_key(
    *,
    hardware: HardwareInfo,
    caps: GpuCompositorCapabilities,
    width: int,
    height: int,
    fps: float,
    pixel_format: str,
    primaries: str,
    transfer: str,
    matrix: str,
    color_range: str,
    layer: OverlayLayer,
) -> GpuCompositorKey:
    return GpuCompositorKey(
        gpu_name=hardware.gpu or "unknown-gpu",
        driver=hardware.driver or "unknown-driver",
        ffmpeg_fingerprint=caps.fingerprint,
        width=max(1, int(width)),
        height=max(1, int(height)),
        fps_milli=max(1, round(float(fps) * 1000.0)),
        pixel_format=str(pixel_format or "unknown"),
        primaries=str(primaries or "unknown"),
        transfer=str(transfer or "unknown"),
        space=str(matrix or "unknown"),
        color_range=str(color_range or "unknown"),
        layer_contract=layer.contract_token(),
    )


def select_gpu_export_route(
    state: OverlayComposerState,
    *,
    hardware: HardwareInfo,
    caps: GpuCompositorCapabilities,
    store: GpuCompositorStore,
    width: int,
    height: int,
    fps: float,
    pixel_format: str,
    primaries: str,
    transfer: str,
    matrix: str,
    color_range: str,
) -> ComposerGpuRoute:
    """Select the narrow H6 fast path or fail closed to CPU reference.

    The first runtime envelope is deliberately one enabled media layer and no
    visualizer.  Multiple layers require a separately benchmarked graph because
    accumulated color/alpha rounding and ordering can differ even if each layer
    passed independently.
    """
    items = state.ordered()
    if len(items) != 1:
        return ComposerGpuRoute(False, "H6 GPU export currently requires exactly one enabled layer")
    item = items[0]
    if item.visualizer is not None:
        return ComposerGpuRoute(False, "procedural/audio-reactive visualizer parity is not physically proven")
    layer = item.media
    if layer is None:
        return ComposerGpuRoute(False, "no media layer is available for H6 GPU export")
    if not hardware.gpu:
        return ComposerGpuRoute(False, "no NVIDIA GPU was detected")
    if not cuda_layer_eligible(layer, caps):
        return ComposerGpuRoute(False, "layer transform/blend is outside the physically benchmarkable CUDA envelope", layer)
    key = build_compositor_key(
        hardware=hardware,
        caps=caps,
        width=width,
        height=height,
        fps=fps,
        pixel_format=pixel_format,
        primaries=primaries,
        transfer=transfer,
        matrix=matrix,
        color_range=color_range,
        layer=layer,
    )
    if not store.approved(key, caps):
        return ComposerGpuRoute(False, "exact H6 GPU/driver/FFmpeg/profile/layer evidence is absent or stale", layer, key)
    return ComposerGpuRoute(True, "exact H6 compositor evidence approved", layer, key)


def default_compositor_evidence_path(cache_root: Path) -> Path:
    return Path(cache_root) / "hardware" / "gpu-compositor.json"
