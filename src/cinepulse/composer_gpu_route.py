from __future__ import annotations

"""Evidence-gated H6 route selection for Preview Composer exports.

This module decides permission only. Capability detection is not enough: the
exact GPU/driver/FFmpeg/base-profile/ordered-stack contract must have a record
produced by the physical H6 benchmark. Projects outside the bounded static
normal-blend envelope remain on the deterministic CPU reference.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorKey,
    GpuCompositorStore,
    OverlayLayer,
    canonical_overlay_stack,
    cuda_stack_eligible,
    overlay_stack_contract_token,
)
from .hardware import HardwareProfile
from .overlay_composer import OverlayComposerState


@dataclass(frozen=True)
class ComposerGpuRoute:
    use_gpu: bool
    reason: str
    layer: OverlayLayer | None = None
    key: GpuCompositorKey | None = None
    layers: tuple[OverlayLayer, ...] = ()


def build_compositor_stack_key(
    *,
    hardware: HardwareProfile,
    caps: GpuCompositorCapabilities,
    width: int,
    height: int,
    fps: float,
    pixel_format: str,
    primaries: str,
    transfer: str,
    matrix: str,
    color_range: str,
    layers: Iterable[OverlayLayer],
) -> GpuCompositorKey:
    ordered = canonical_overlay_stack(layers)
    if not ordered:
        raise ValueError("compositor key requires at least one layer")
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
        layer_contract=overlay_stack_contract_token(ordered),
    )


def build_compositor_key(
    *,
    hardware: HardwareProfile,
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
    """Compatibility helper; schema 3 binds even one layer as a one-item stack."""
    return build_compositor_stack_key(
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
        layers=(layer,),
    )


def select_gpu_export_route(
    state: OverlayComposerState,
    *,
    hardware: HardwareProfile,
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
    """Select the bounded H6 fast path or fail closed to CPU reference.

    The entire ordered static stack is one evidence unit. Individual approvals
    cannot be composed transitively; the physical benchmark must prove the
    exact stack because alpha rounding and z-order interact across layers.
    """
    items = state.ordered()
    if not items:
        return ComposerGpuRoute(False, "no media layer is available for H6 GPU export")
    if any(item.visualizer is not None for item in items):
        return ComposerGpuRoute(False, "procedural/audio-reactive visualizer parity is not physically proven")
    if any(item.media is None for item in items):
        return ComposerGpuRoute(False, "H6 CUDA route contains a non-media Composer item")
    layers = canonical_overlay_stack(item.media for item in items if item.media is not None)
    first = layers[0] if layers else None
    if not hardware.gpu:
        return ComposerGpuRoute(False, "no NVIDIA GPU was detected", first, layers=layers)
    if not cuda_stack_eligible(layers, caps):
        return ComposerGpuRoute(
            False,
            "ordered layer stack is outside the bounded physically benchmarkable CUDA envelope",
            first,
            layers=layers,
        )
    key = build_compositor_stack_key(
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
        layers=layers,
    )
    if not store.approved(key, caps):
        return ComposerGpuRoute(
            False,
            "exact H6 GPU/driver/FFmpeg/profile/ordered-stack evidence is absent or stale",
            first,
            key,
            layers,
        )
    return ComposerGpuRoute(True, "exact H6 compositor stack evidence approved", first, key, layers)


def default_compositor_evidence_path(cache_root: Path) -> Path:
    return Path(cache_root) / "hardware" / "gpu-compositor.json"
