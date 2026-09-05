from __future__ import annotations

"""Preview-only Overlay Composer / Music Visualizer model.

This module is deliberately independent from Stable ``RenderSettings``. It
models the requested layer controls and chooses an execution route per layer,
but capability alone never unlocks the CUDA compositor: exact H6 evidence is
required. Unsupported transforms/reactivity remain on the established CPU path.

The composer state is persistable as a small versioned JSON document. Reactive
frame evaluation is pure and deterministic so preview, CPU rendering and any
future evidence-gated shader backend can consume the same geometry contract.
"""

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Literal

from .gpu_compositor import (
    GpuCompositorCapabilities,
    GpuCompositorKey,
    GpuCompositorStore,
    OverlayLayer,
    cuda_layer_eligible,
)


COMPOSER_SCHEMA = 1
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
        if self.binding not in {"master", "vocals", "drums", "bass", "other"}:
            raise ValueError("unsupported visualizer audio binding")
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
class ReactiveFrameState:
    """Normalized per-frame transform shared by preview/CPU/future GPU routes."""

    x: float
    y: float
    scale: float
    opacity: float
    rotation_degrees: float
    reaction: float


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
        return {"schema": COMPOSER_SCHEMA, "items": [asdict(item) for item in self.items]}

    @classmethod
    def from_dict(cls, payload: object) -> "OverlayComposerState":
        if not isinstance(payload, dict) or payload.get("schema") != COMPOSER_SCHEMA:
            raise ValueError("unsupported overlay composer schema")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("overlay composer items must be a list")
        state = cls()
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ValueError("overlay composer item must be an object")
            item_id = str(raw.get("id") or "").strip()
            enabled = bool(raw.get("enabled", True))
            media_raw = raw.get("media")
            visualizer_raw = raw.get("visualizer")
            if bool(media_raw) == bool(visualizer_raw):
                raise ValueError("persisted composer item must contain exactly one layer")
            media = OverlayLayer(**media_raw) if isinstance(media_raw, dict) else None
            visualizer = VisualizerLayer(**visualizer_raw) if isinstance(visualizer_raw, dict) else None
            state.add(ComposerItem(item_id, media=media, visualizer=visualizer, enabled=enabled))
        return state

    def save(self, path: Path) -> None:
        """Atomically persist Preview composer state without touching Stable config."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(self.as_dict(), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def load(cls, path: Path) -> "OverlayComposerState":
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not load overlay composer state: {exc}") from exc
        return cls.from_dict(payload)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _rotation(base: float, spin_rpm: float, time_seconds: float) -> float:
    # rpm * 360 / 60 == degrees per second. Keep values bounded to make
    # serialized preview snapshots deterministic after very long projects.
    value = float(base) + float(spin_rpm) * 6.0 * max(0.0, float(time_seconds))
    return math.fmod(value, 360.0)


def evaluate_media_frame(
    layer: OverlayLayer,
    *,
    time_seconds: float,
    rms: float = 0.0,
    onset: float = 0.0,
) -> ReactiveFrameState:
    """Resolve requested pulse/beat/spin without changing the layer contract."""
    loudness = _clamp01(rms)
    attack = _clamp01(onset)
    reaction = _clamp01(loudness * max(0.0, layer.pulse) * 0.55 + attack * max(0.0, layer.beat_reaction) * 0.75)
    scale = max(0.01, min(16.0, float(layer.scale) * (1.0 + reaction * 0.18)))
    return ReactiveFrameState(
        x=float(layer.x),
        y=float(layer.y),
        scale=scale,
        opacity=float(layer.opacity),
        rotation_degrees=_rotation(layer.rotation_degrees, layer.spin_rpm, time_seconds),
        reaction=reaction,
    )


def evaluate_visualizer_frame(
    layer: VisualizerLayer,
    *,
    time_seconds: float,
    rms: float,
    onset: float,
    band_energy: float,
) -> ReactiveFrameState:
    """Compute one deterministic audio-reactive visualizer transform.

    The caller supplies the already-selected master/stem envelope. This keeps
    audio binding outside rendering math and guarantees preview/final parity.
    """
    combined = _clamp01(_clamp01(rms) * 0.50 + _clamp01(band_energy) * 0.30 + _clamp01(onset) * 0.65)
    reaction = _clamp01(combined * max(0.0, float(layer.reaction)))
    scale = max(0.01, min(16.0, float(layer.scale) * (1.0 + reaction * 0.16)))
    return ReactiveFrameState(
        x=float(layer.x),
        y=float(layer.y),
        scale=scale,
        opacity=float(layer.opacity),
        rotation_degrees=_rotation(layer.rotation_degrees, layer.spin_rpm, time_seconds),
        reaction=reaction,
    )


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
