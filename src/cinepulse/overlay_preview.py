from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .overlay_composer import OverlayLayer, OverlayScene, OverlaySceneError, VisualizerSpec


@dataclass(frozen=True)
class AudioReactiveState:
    bands: tuple[float, float, float] = (0.72, 0.55, 0.44)
    loudness: float = 0.66
    attack: float = 0.48
    phase: float = 0.0

    def normalized(self) -> "AudioReactiveState":
        bands = tuple(max(0.0, min(1.0, float(value))) for value in self.bands)
        return AudioReactiveState(
            bands=(bands[0], bands[1], bands[2]),
            loudness=max(0.0, min(1.0, float(self.loudness))),
            attack=max(0.0, min(1.0, float(self.attack))),
            phase=float(self.phase) % 1.0,
        )


def _rgb(hex_color: str) -> np.ndarray:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        raise OverlaySceneError("Cor precisa usar #RRGGBB.")
    try:
        return np.asarray(tuple(int(value[index : index + 2], 16) for index in (0, 2, 4)), dtype=np.float32)
    except ValueError as exc:
        raise OverlaySceneError("Cor precisa usar #RRGGBB.") from exc


def resize_rgba_nearest(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if image.ndim != 3 or image.shape[2] != 4:
        raise OverlaySceneError("Overlay precisa ser RGBA.")
    width = max(1, int(width))
    height = max(1, int(height))
    src_h, src_w = image.shape[:2]
    xs = np.minimum((np.arange(width) * src_w / width).astype(np.int32), src_w - 1)
    ys = np.minimum((np.arange(height) * src_h / height).astype(np.int32), src_h - 1)
    return image[ys[:, None], xs[None, :]].copy()


def rotate_rgba_nearest(image: np.ndarray, degrees: float) -> np.ndarray:
    degrees = float(degrees)
    if abs(degrees) < 1e-6:
        return image
    h, w = image.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    radians = math.radians(-degrees)
    cos_a = math.cos(radians)
    sin_a = math.sin(radians)
    rel_x = xx - cx
    rel_y = yy - cy
    src_x = np.rint(rel_x * cos_a - rel_y * sin_a + cx).astype(np.int32)
    src_y = np.rint(rel_x * sin_a + rel_y * cos_a + cy).astype(np.int32)
    valid = (src_x >= 0) & (src_x < w) & (src_y >= 0) & (src_y < h)
    out = np.zeros_like(image)
    out[valid] = image[src_y[valid], src_x[valid]]
    return out


def composite_rgba_at(
    base_rgb: np.ndarray,
    overlay_rgba: np.ndarray,
    *,
    x: int,
    y: int,
    opacity: float = 1.0,
    rotation_deg: float = 0.0,
) -> np.ndarray:
    if base_rgb.ndim != 3 or base_rgb.shape[2] != 3:
        raise OverlaySceneError("Base precisa ser RGB.")
    overlay = rotate_rgba_nearest(overlay_rgba, rotation_deg)
    base_h, base_w = base_rgb.shape[:2]
    over_h, over_w = overlay.shape[:2]
    left = max(0, int(x))
    top = max(0, int(y))
    right = min(base_w, int(x) + over_w)
    bottom = min(base_h, int(y) + over_h)
    if right <= left or bottom <= top:
        return base_rgb.copy()
    src_left = left - int(x)
    src_top = top - int(y)
    src_right = src_left + (right - left)
    src_bottom = src_top + (bottom - top)
    source = overlay[src_top:src_bottom, src_left:src_right]
    alpha = source[..., 3:4].astype(np.float32) / 255.0
    alpha *= max(0.0, min(1.0, float(opacity)))
    out = base_rgb.copy().astype(np.float32)
    target = out[top:bottom, left:right]
    target[:] = target * (1.0 - alpha) + source[..., :3].astype(np.float32) * alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def _draw_disc(frame: np.ndarray, x: int, y: int, radius: int, color: np.ndarray, alpha: int) -> None:
    h, w = frame.shape[:2]
    radius = max(1, int(radius))
    x0, x1 = max(0, x - radius), min(w, x + radius + 1)
    y0, y1 = max(0, y - radius), min(h, y + radius + 1)
    if x1 <= x0 or y1 <= y0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    mask = (xx - x) ** 2 + (yy - y) ** 2 <= radius**2
    frame[y0:y1, x0:x1, :3][mask] = np.asarray(color, dtype=np.uint8)
    frame[y0:y1, x0:x1, 3][mask] = np.uint8(alpha)


def _draw_line(frame: np.ndarray, points: list[tuple[int, int]], color: np.ndarray, thickness: int, alpha: int) -> None:
    if len(points) < 2:
        return
    radius = max(1, int(round(thickness / 2)))
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        distance = max(abs(x1 - x0), abs(y1 - y0), 1)
        for step in range(distance + 1):
            mix = step / distance
            x = int(round(x0 + (x1 - x0) * mix))
            y = int(round(y0 + (y1 - y0) * mix))
            _draw_disc(frame, x, y, radius, color, alpha)


def _draw_gradient_line(
    frame: np.ndarray,
    points: list[tuple[int, int]],
    primary: np.ndarray,
    secondary: np.ndarray,
    thickness: int,
    alpha: int,
) -> None:
    if len(points) < 2:
        return
    denominator = max(1, len(points) - 2)
    for index, (start, end) in enumerate(zip(points, points[1:])):
        mix = index / denominator
        color = np.clip(primary * (1.0 - mix) + secondary * mix, 0, 255).astype(np.uint8)
        _draw_line(frame, [start, end], color, thickness, alpha)


def _focus_gain(spec: VisualizerSpec, state: AudioReactiveState) -> float:
    bass, mids, highs = state.bands
    if spec.focus == "bass":
        value = bass
    elif spec.focus == "mids":
        value = mids
    elif spec.focus == "highs":
        value = highs
    elif spec.focus == "beats":
        value = max(state.attack, bass * 0.7)
    else:
        value = bass * 0.40 + mids * 0.34 + highs * 0.26
    return max(0.02, min(1.0, value * spec.sensitivity))


def _spectral_value(nx: float, spec: VisualizerSpec, state: AudioReactiveState, index: int) -> float:
    bass, mids, highs = state.bands
    bass_curve = bass * (1.0 - nx) ** 1.8
    mid_curve = mids * max(0.0, 1.0 - abs(nx - 0.5) * 1.6)
    high_curve = highs * nx**1.6
    spectral = max(0.0, bass_curve + mid_curve + high_curve) / 1.7
    ripple = 0.88 + 0.12 * math.sin(math.tau * (nx * 2.6 + state.phase + index * 0.009))
    return max(0.025, min(1.0, spectral * ripple * spec.sensitivity))


def render_visualizer_rgba(
    width: int,
    height: int,
    spec: VisualizerSpec,
    state: AudioReactiveState | None = None,
    *,
    opacity: float = 1.0,
) -> np.ndarray:
    spec.validate()
    state = (state or AudioReactiveState()).normalized()
    width = max(8, int(width))
    height = max(8, int(height))
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    primary = _rgb(spec.color)
    secondary = _rgb(spec.secondary_color)
    alpha = int(round(255 * max(0.0, min(1.0, float(opacity)))))
    gain = _focus_gain(spec, state)
    center = (height - 1) / 2.0

    if spec.style == "waveform":
        samples = max(24, min(width, 420))
        thickness = max(1, int(round(spec.thickness * max(2.0, height * 0.08))))
        points: list[tuple[int, int]] = []
        for index in range(samples):
            nx = index / max(1, samples - 1)
            carrier = (
                math.sin(math.tau * (2.0 * nx + state.phase)) * 0.58
                + math.sin(math.tau * (5.0 * nx + state.phase * 0.71)) * 0.27
                + math.sin(math.tau * (11.0 * nx + state.phase * 1.31)) * 0.15
            )
            attack_boost = 0.72 + state.attack * 0.52
            amplitude = min(0.46, 0.04 + gain * 0.40 * attack_boost)
            y = int(round(center + carrier * amplitude * height))
            x = int(round(nx * (width - 1)))
            points.append((x, y))
        _draw_line(frame, points, primary, thickness, alpha)
        return frame

    if spec.style == "spectrum":
        samples = max(24, min(width, 420))
        thickness = max(1, int(round(spec.thickness * max(2.0, height * 0.08))))
        lower: list[tuple[int, int]] = []
        upper: list[tuple[int, int]] = []
        for index in range(samples):
            nx = index / max(1, samples - 1)
            value = _spectral_value(nx, spec, state, index)
            x = int(round(nx * (width - 1)))
            if spec.mirror:
                excursion = value * max(1.0, center * 0.90)
                upper.append((x, int(round(center - excursion))))
                lower.append((x, int(round(center + excursion))))
            else:
                y = int(round((height - 1) - value * height * 0.86))
                lower.append((x, y))
        if spec.mirror:
            _draw_gradient_line(frame, upper, primary, secondary, thickness, alpha)
        _draw_gradient_line(frame, lower, primary, secondary, thickness, alpha)
        return frame

    count = max(4, min(int(spec.bars), max(4, width // 2)))
    gap = max(1, width // max(24, count * 6))
    cell = width / count
    for index in range(count):
        nx = (index + 0.5) / count
        harmonic = 0.55 + 0.45 * math.sin(math.tau * (nx * 2.3 + state.phase + index * 0.013))
        value = _spectral_value(nx, spec, state, index)
        value = max(value * 0.72, gain * (0.60 + 0.40 * harmonic))
        bar_height = max(1, int(round(value * height * (0.92 if spec.mirror else 0.86))))
        bar_width = max(1, int(round(cell - gap)))
        x0 = min(width - 1, int(round(index * cell + gap / 2)))
        x1 = min(width, x0 + bar_width)
        mix = index / max(1, count - 1)
        color = np.clip(primary * (1.0 - mix) + secondary * mix, 0, 255).astype(np.uint8)
        if spec.mirror:
            half = max(1, bar_height // 2)
            y0 = max(0, int(round(center)) - half)
            y1 = min(height, int(round(center)) + half + 1)
        else:
            y1 = height
            y0 = max(0, height - bar_height)
        frame[y0:y1, x0:x1, :3] = color
        frame[y0:y1, x0:x1, 3] = np.uint8(alpha)
    return frame


def render_scene_preview(
    base_rgb: np.ndarray,
    scene: OverlayScene,
    *,
    asset_frames: dict[str, np.ndarray] | None = None,
    audio_state: AudioReactiveState | None = None,
) -> np.ndarray:
    scene.validate()
    asset_frames = asset_frames or {}
    output = base_rgb.copy()
    height, width = output.shape[:2]
    for layer in scene.active_layers:
        x, y, target_width, target_height = layer.transform.rect.pixels(width, height)
        if layer.kind == "asset":
            frame = asset_frames.get(layer.id)
            if frame is None:
                continue
            if frame.shape[:2] != (target_height, target_width):
                frame = resize_rgba_nearest(frame, target_width, target_height)
        else:
            assert layer.visualizer is not None
            frame = render_visualizer_rgba(target_width, target_height, layer.visualizer, audio_state)
        output = composite_rgba_at(
            output,
            frame,
            x=x,
            y=y,
            opacity=layer.transform.opacity,
            rotation_deg=layer.transform.rotation_deg,
        )
    return output
