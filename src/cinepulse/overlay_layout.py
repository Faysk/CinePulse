from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .overlay_composer import NormalizedRect, OverlayLayer, OverlayScene, OverlaySceneError


@dataclass(frozen=True)
class SafeArea:
    key: str
    label: str
    rect: NormalizedRect
    note: str


SAFE_AREAS: dict[str, SafeArea] = {
    "none": SafeArea("none", "Sem guia", NormalizedRect(0.0, 0.0, 1.0, 1.0), "Canvas completo."),
    "frame": SafeArea(
        "frame", "Margem segura 5%", NormalizedRect(0.05, 0.05, 0.90, 0.90),
        "Guia genérica para manter elementos longe das bordas.",
    ),
    "vertical-social": SafeArea(
        "vertical-social", "Vertical social", NormalizedRect(0.08, 0.08, 0.72, 0.76),
        "Guia conservadora; interfaces de Shorts/Reels/TikTok podem mudar e devem ser conferidas antes de publicar.",
    ),
}


@dataclass(frozen=True)
class SnapResult:
    rect: NormalizedRect
    guides_x: tuple[float, ...] = ()
    guides_y: tuple[float, ...] = ()


def safe_area(key: str) -> SafeArea:
    try:
        return SAFE_AREAS[key]
    except KeyError as exc:
        raise OverlaySceneError(f"Guia de área segura desconhecida: {key}") from exc


def point_to_normalized(x: float, y: float, canvas_width: int, canvas_height: int) -> tuple[float, float]:
    if canvas_width <= 0 or canvas_height <= 0:
        raise OverlaySceneError("Canvas inválido para coordenadas do editor.")
    return float(x) / canvas_width, float(y) / canvas_height


def delta_to_normalized(dx: float, dy: float, canvas_width: int, canvas_height: int) -> tuple[float, float]:
    return point_to_normalized(dx, dy, canvas_width, canvas_height)


def hit_test(scene: OverlayScene, x: float, y: float, canvas_width: int, canvas_height: int) -> str | None:
    """Return the visually top-most unlocked or locked active layer under a point."""
    nx, ny = point_to_normalized(x, y, canvas_width, canvas_height)
    for layer in reversed(scene.active_layers):
        rect = layer.transform.rect
        if rect.x <= nx <= rect.x + rect.width and rect.y <= ny <= rect.y + rect.height:
            return layer.id
    return None


def resize_rect(
    rect: NormalizedRect,
    *,
    dw: float,
    dh: float,
    preserve_aspect: bool,
    source_aspect: float | None = None,
    min_size: float = 0.01,
) -> NormalizedRect:
    width = max(min_size, rect.width + float(dw))
    height = max(min_size, rect.height + float(dh))
    if preserve_aspect:
        aspect = float(source_aspect or (rect.width / max(rect.height, 1e-9)))
        if aspect <= 0:
            raise OverlaySceneError("Aspect ratio precisa ser positivo.")
        if abs(dw) >= abs(dh):
            height = width / aspect
        else:
            width = height * aspect
    result = NormalizedRect(rect.x, rect.y, width, height)
    result.validate()
    return result


def _candidate_edges(rect: NormalizedRect) -> tuple[tuple[str, float], ...]:
    return (
        ("left", rect.x),
        ("center", rect.x + rect.width / 2.0),
        ("right", rect.x + rect.width),
    )


def _candidate_vertical(rect: NormalizedRect) -> tuple[tuple[str, float], ...]:
    return (
        ("top", rect.y),
        ("middle", rect.y + rect.height / 2.0),
        ("bottom", rect.y + rect.height),
    )


def snap_rect(
    rect: NormalizedRect,
    *,
    other_rects: Iterable[NormalizedRect] = (),
    threshold: float = 0.012,
    include_canvas: bool = True,
    safe_area_key: str | None = None,
) -> SnapResult:
    """Snap a moving rectangle to canvas, safe-area and neighboring edges."""
    threshold = max(0.0, float(threshold))
    x_targets: list[float] = []
    y_targets: list[float] = []
    if include_canvas:
        x_targets.extend((0.0, 0.5, 1.0))
        y_targets.extend((0.0, 0.5, 1.0))
    if safe_area_key and safe_area_key != "none":
        guide = safe_area(safe_area_key).rect
        x_targets.extend(value for _name, value in _candidate_edges(guide))
        y_targets.extend(value for _name, value in _candidate_vertical(guide))
    for other in other_rects:
        x_targets.extend(value for _name, value in _candidate_edges(other))
        y_targets.extend(value for _name, value in _candidate_vertical(other))

    best_dx: float | None = None
    best_x: float | None = None
    for _name, edge in _candidate_edges(rect):
        for target in x_targets:
            delta = target - edge
            if abs(delta) <= threshold and (best_dx is None or abs(delta) < abs(best_dx)):
                best_dx = delta
                best_x = target

    best_dy: float | None = None
    best_y: float | None = None
    for _name, edge in _candidate_vertical(rect):
        for target in y_targets:
            delta = target - edge
            if abs(delta) <= threshold and (best_dy is None or abs(delta) < abs(best_dy)):
                best_dy = delta
                best_y = target

    snapped = rect.moved(best_dx or 0.0, best_dy or 0.0)
    snapped.validate()
    return SnapResult(
        snapped,
        () if best_x is None else (best_x,),
        () if best_y is None else (best_y,),
    )


def other_layer_rects(scene: OverlayScene, excluded_ids: Iterable[str]) -> tuple[NormalizedRect, ...]:
    excluded = set(excluded_ids)
    return tuple(layer.transform.rect for layer in scene.active_layers if layer.id not in excluded)
