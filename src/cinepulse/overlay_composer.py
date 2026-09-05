from __future__ import annotations

"""Preview-only Overlay Composer / Music Visualizer model.

This module is deliberately independent from Stable ``RenderSettings``. It
models the requested layer controls and chooses an execution route per layer,
but capability alone never unlocks the CUDA compositor: exact H6 evidence is
required. Unsupported transforms/reactivity remain on the established CPU path.
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from .gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorKey,
    GpuCompositorStore,
    OverlayLayer,
    cuda_layer_eligible,
)


VisualizerKind = Literal["waveform", "spectrum", "circular"]
VisualizerBinding = Literal["master", "vocals", "drums", "bass", "other"]
ExecutionRoute = Literal["cuda-overlay", "cpu-overlay", "cpu-visualizer"]

_MEDIA_KINDS = {
    ".png": "png",
    ".gif": "gif",
    ".apng": "apng",
    ".webp": "webp",
    ".mov": "video-alpha",
    ".webm": "video-alpha",
    ".mkv": "video-alpha",
    ".mp4": "video-alpha",
}


@dataclass(frozen=True)
class VisualizerLayer:
    kind: VisualizerKind
    x: float = 0.5
    y: float = 0.5
    scale: float = 1.0
    opacity: float = 1.0
    z_order: int = 0
    binding: VisualizerBinding = "master"
    smoothing: float = 0.65
    reaction: float = 1.0
    thickness: float = 1.0
    bars: int = 64
    rotation_degrees: float = 0.0
    spin_rpm: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in {"waveform", "spectrum", "circular"}:
            raise ValueError("unsupported visualizer kind")
        if not 0.0 <= self.x <= 1.0 or not 0.0 <= self.y <= 1.0:
            raise ValueError("visualizer x/y must be normalized to 0..1")
        if not 0.01 <= self.scale <= 16.0:
            raise ValueError("visualizer scale must be within 0.01..16")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError("visualizer opacity must be within 0..1")
        if not 0.0 <= self.smoothing <= 1.0:
            raise ValueError("visualizer smoothing must be within 0..1")
        if not 0.0 <= self.reaction <= 2.0:
            raise ValueError("visualizer reaction must be within 0..2")
        if not 0.25 <= self.thickness <= 8.0:
            raise ValueError("visualizer thickness must be within 0.25..8")
        if not 8 <= self.bars <= 512:
            raise ValueError("visualizer bars must be within 8..512")


@dataclass(frozen=True)
class ComposerItem:
    id: str
    media: OverlayLayer | None = None
    visualizer: VisualizerLayer | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if bool(self.media) == bool(self.visualizer):
            raise ValueError("composer item must contain exactly one media or visualizer layer")
        if not self.id.strip():
            raise ValueError("composer item requires an id")

    @property
    def z_order(self) -> int:
        return self.media.z_order if self.media is not None else self.visualizer.z_order  # type: ignore[union-attr]


@dataclass(frozen=True)
class ComposerRoute:
    item_id: str
    route: ExecutionRoute
    reason: str


@dataclass
class OverlayComposerState:
    items: list[ComposerItem] = field(default_factory=list)

    def add(self, item: ComposerItem) -> None:
        if any(existing.id == item.id for existing in self.items):
            raise ValueError(f"duplicate composer item id: {item.id}")
        self.items.append(item)

    def remove(self, item_id: str) -> bool:
        before = len(self.items)
        self.items[:] = [item for item in self.items if item.id != item_id]
        return len(self.items) != before

    def ordered(self) -> tuple[ComposerItem, ...]:
        return tuple(sorted((item for item in self.items if item.enabled), key=lambda item: (item.z_order, item.id)))

    def as_dict(self) -> dict[str, object]:
        return {"schema": 1, "items": [asdict(item) for item in self.items]}


def media_layer_from_path(path: str | Path, **kwargs: object) -> OverlayLayer:
    source = Path(path)
    suffix = source.suffix.lower()
    kind = _MEDIA_KINDS.get(suffix)
    if not kind:
        raise ValueError(f"unsupported overlay media extension: {suffix or '<none>'}")
    return OverlayLayer(str(source), kind, **kwargs)  # type: ignore[arg-type]


def route_item(
    item: ComposerItem,
    *,
    caps: GpuCompositorCapabilities,
    store: GpuCompositorStore,
    compositor_key: GpuCompositorKey | None,
) -> ComposerRoute:
    """Choose a fail-closed route without changing the requested appearance."""
    if item.visualizer is not None:
        return ComposerRoute(
            item.id,
            "cpu-visualizer",
            "procedural/audio-reactive shader parity is not yet physically proven; preserve CPU renderer",
        )
    layer = item.media
    assert layer is not None
    if compositor_key is None:
        return ComposerRoute(item.id, "cpu-overlay", "no exact H6 compositor evidence key is available")
    if not cuda_layer_eligible(layer, caps):
        return ComposerRoute(item.id, "cpu-overlay", "layer transform/blend is outside the proven CUDA envelope")
    if not store.approved(compositor_key, caps):
        return ComposerRoute(item.id, "cpu-overlay", "exact H6 CUDA evidence is absent or stale")
    if compositor_key.layer_contract != layer.contract_token():
        return ComposerRoute(item.id, "cpu-overlay", "H6 evidence belongs to a different layer contract")
    return ComposerRoute(item.id, "cuda-overlay", "exact H6 visual-parity and throughput evidence approved")


def route_project(
    state: OverlayComposerState,
    *,
    caps: GpuCompositorCapabilities,
    store: GpuCompositorStore,
    keys: dict[str, GpuCompositorKey],
) -> tuple[ComposerRoute, ...]:
    return tuple(
        route_item(item, caps=caps, store=store, compositor_key=keys.get(item.id))
        for item in state.ordered()
    )
