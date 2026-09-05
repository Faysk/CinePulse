from __future__ import annotations

"""Deterministic CPU reference renderer for Preview music visualizers.

This renderer is intentionally simple and dependency-light. It is the visual
reference for preview/final parity and for any later shader benchmark; GPU
implementations are optimizations of this contract, not a separate design.
"""

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .overlay_composer import ReactiveFrameState, VisualizerLayer, visualizer_geometry
from .visualizer_geometry import Bar, Point, RadialBar


@dataclass(frozen=True)
class VisualizerColor:
    r: int = 255
    g: int = 255
    b: int = 255

    def rgb(self) -> np.ndarray:
        return np.asarray(
            [max(0, min(255, int(self.r))), max(0, min(255, int(self.g))), max(0, min(255, int(self.b)))],
            dtype=np.uint8,
        )


def _pixel(point: Point, width: int, height: int, state: ReactiveFrameState) -> tuple[int, int]:
    # Geometry is local normalized 0..1. Apply layer scale around local center,
    # then place that center at state x/y on the final canvas.
    local_x = (point.x - 0.5) * state.scale
    local_y = (point.y - 0.5) * state.scale
    x = state.x * (width - 1) + local_x * width
    y = state.y * (height - 1) + local_y * height
    return int(round(x)), int(round(y))


def _stamp(canvas: np.ndarray, x: int, y: int, radius: int, rgb: np.ndarray, alpha: int) -> None:
    height, width = canvas.shape[:2]
    if x + radius < 0 or y + radius < 0 or x - radius >= width or y - radius >= height:
        return
    x0, x1 = max(0, x - radius), min(width - 1, x + radius)
    y0, y1 = max(0, y - radius), min(height - 1, y + radius)
    yy, xx = np.ogrid[y0:y1 + 1, x0:x1 + 1]
    mask = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
    region = canvas[y0:y1 + 1, x0:x1 + 1]
    region[mask, :3] = rgb
    region[mask, 3] = np.maximum(region[mask, 3], alpha)


def _line(canvas: np.ndarray, start: tuple[int, int], end: tuple[int, int], thickness: int, rgb: np.ndarray, alpha: int) -> None:
    x0, y0 = start
    x1, y1 = end
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    xs = np.rint(np.linspace(x0, x1, steps + 1)).astype(np.int32)
    ys = np.rint(np.linspace(y0, y1, steps + 1)).astype(np.int32)
    radius = max(0, (thickness - 1) // 2)
    for x, y in zip(xs, ys):
        _stamp(canvas, int(x), int(y), radius, rgb, alpha)


def render_visualizer_rgba(
    layer: VisualizerLayer,
    values: Iterable[float],
    frame_state: ReactiveFrameState,
    *,
    width: int,
    height: int,
    color: VisualizerColor = VisualizerColor(),
) -> np.ndarray:
    """Render one transparent RGBA frame following the shared geometry contract."""
    width = max(1, int(width))
    height = max(1, int(height))
    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    rgb = color.rgb()
    alpha = int(round(max(0.0, min(1.0, frame_state.opacity)) * 255.0))
    thickness = max(1, int(round(layer.thickness)))
    geometry = visualizer_geometry(layer, values, frame_state)

    if layer.kind == "waveform":
        points = tuple(geometry)
        for first, second in zip(points, points[1:]):
            _line(canvas, _pixel(first, width, height, frame_state), _pixel(second, width, height, frame_state), thickness, rgb, alpha)
        return canvas

    if layer.kind == "spectrum":
        for bar in geometry:
            assert isinstance(bar, Bar)
            start = _pixel(Point((bar.x0 + bar.x1) * 0.5, bar.y0), width, height, frame_state)
            end = _pixel(Point((bar.x0 + bar.x1) * 0.5, bar.y1), width, height, frame_state)
            bar_width = max(thickness, int(round(max(0.0, bar.x1 - bar.x0) * width * frame_state.scale)))
            _line(canvas, start, end, bar_width, rgb, alpha)
        return canvas

    if layer.kind == "circular":
        for bar in geometry:
            assert isinstance(bar, RadialBar)
            _line(canvas, _pixel(bar.inner, width, height, frame_state), _pixel(bar.outer, width, height, frame_state), thickness, rgb, alpha)
        return canvas

    raise ValueError(f"unsupported visualizer kind: {layer.kind}")
