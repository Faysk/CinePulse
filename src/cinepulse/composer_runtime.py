from __future__ import annotations

"""Deterministic Preview Overlay Composer CPU reference runtime.

The runtime intentionally operates on decoded RGBA assets. Media decoding and
playback selection live in ``composer_media``; visualizer geometry/rendering
live in their own backend-neutral modules. This separation gives H6 one exact
CPU visual reference that future CUDA/shader routes must reproduce.

Nothing in this module mutates Stable RenderSettings or chooses a GPU merely
because one exists.
"""

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from .overlay_composer import (
    OverlayComposerState,
    ReactiveFrameState,
    evaluate_media_frame,
    evaluate_visualizer_frame,
)
from .visualizer_renderer import VisualizerColor, render_visualizer_rgba
from .composer_resample import resize_bilinear_rgba, rotate_bilinear_rgba


@dataclass(frozen=True)
class AudioFrameFeatures:
    rms: float = 0.0
    onset: float = 0.0
    band_energy: float = 0.0
    values: tuple[float, ...] = ()


@dataclass(frozen=True)
class ComposerFrameInputs:
    project_time: float
    media_rgba: Mapping[str, np.ndarray]
    audio: Mapping[str, AudioFrameFeatures]


def _validate_base(frame: np.ndarray) -> np.ndarray:
    value = np.asarray(frame)
    if value.ndim != 3 or value.shape[2] not in (3, 4):
        raise ValueError("composer base frame must be HxWxRGB/RGBA")
    if value.dtype != np.uint8:
        raise ValueError("composer base frame must use uint8 reference pixels")
    if value.shape[2] == 4:
        return value.copy()
    alpha = np.full(value.shape[:2] + (1,), 255, dtype=np.uint8)
    return np.concatenate((value, alpha), axis=2)


def _validate_overlay(frame: np.ndarray) -> np.ndarray:
    value = np.asarray(frame)
    if value.ndim != 3 or value.shape[2] != 4 or value.dtype != np.uint8:
        raise ValueError("composer overlay must be uint8 HxWxRGBA")
    return value


def transform_overlay(
    source: np.ndarray,
    state: ReactiveFrameState,
    canvas_width: int,
    canvas_height: int,
) -> tuple[np.ndarray, int, int]:
    overlay = _validate_overlay(source)
    target_w = max(1, int(round(overlay.shape[1] * max(0.01, float(state.scale)))))
    target_h = max(1, int(round(overlay.shape[0] * max(0.01, float(state.scale)))))
    overlay = resize_bilinear_rgba(overlay, target_w, target_h)
    overlay = rotate_bilinear_rgba(overlay, state.rotation_degrees)
    if state.opacity < 1.0:
        overlay = overlay.copy()
        overlay[..., 3] = np.rint(
            overlay[..., 3].astype(np.float32)
            * max(0.0, min(1.0, state.opacity))
        ).astype(np.uint8)
    center_x = float(state.x) * max(0, int(canvas_width) - 1)
    center_y = float(state.y) * max(0, int(canvas_height) - 1)
    left = int(round(center_x - (overlay.shape[1] - 1) * 0.5))
    top = int(round(center_y - (overlay.shape[0] - 1) * 0.5))
    return overlay, left, top


def _blend_rgb(dst: np.ndarray, src: np.ndarray, mode: str) -> np.ndarray:
    if mode == "normal":
        return src
    if mode == "multiply":
        return dst * src
    if mode == "screen":
        return 1.0 - (1.0 - dst) * (1.0 - src)
    if mode == "add":
        return np.minimum(1.0, dst + src)
    if mode == "overlay":
        return np.where(
            dst <= 0.5,
            2.0 * dst * src,
            1.0 - 2.0 * (1.0 - dst) * (1.0 - src),
        )
    raise ValueError(f"unsupported composer blend mode: {mode}")


def blend_over(
    base: np.ndarray,
    overlay: np.ndarray,
    left: int,
    top: int,
    *,
    mode: str = "normal",
) -> None:
    """Straight-alpha compositing with a deterministic separable blend mode.

    The W3C/PDF-style blend equation is used for partially transparent source
    and destination pixels. ``normal`` is therefore exactly the same source-over
    contract as the original reference, while multiply/screen/add/overlay alter
    only the overlap color term. All math remains float32 and rounds once when
    writing the uint8 reference pixel.
    """
    if (
        not isinstance(base, np.ndarray)
        or base.ndim != 3
        or base.shape[2] != 4
        or base.dtype != np.uint8
    ):
        raise ValueError("composer alpha base must be uint8 HxWxRGBA")
    if mode not in {"normal", "multiply", "screen", "add", "overlay"}:
        raise ValueError(f"unsupported composer blend mode: {mode}")
    over = _validate_overlay(overlay)
    canvas_h, canvas_w = base.shape[:2]
    over_h, over_w = over.shape[:2]
    x0 = max(0, int(left))
    y0 = max(0, int(top))
    x1 = min(canvas_w, int(left) + over_w)
    y1 = min(canvas_h, int(top) + over_h)
    if x0 >= x1 or y0 >= y1:
        return
    ox0 = x0 - int(left)
    oy0 = y0 - int(top)
    src = over[
        oy0:oy0 + (y1 - y0),
        ox0:ox0 + (x1 - x0),
    ].astype(np.float32) / 255.0
    dst = base[y0:y1, x0:x1].astype(np.float32) / 255.0
    sa = src[..., 3:4]
    da = dst[..., 3:4]
    blend = _blend_rgb(dst[..., :3], src[..., :3], mode)
    out_a = sa + da * (1.0 - sa)
    premul = (
        src[..., :3] * sa * (1.0 - da)
        + dst[..., :3] * da * (1.0 - sa)
        + blend * sa * da
    )
    out_rgb = np.divide(
        premul,
        np.maximum(out_a, 1e-8),
        out=np.zeros_like(premul),
        where=out_a > 1e-8,
    )
    result = np.concatenate((out_rgb, out_a), axis=2)
    base[y0:y1, x0:x1] = np.clip(
        np.rint(result * 255.0),
        0,
        255,
    ).astype(np.uint8)


def alpha_over(base: np.ndarray, overlay: np.ndarray, left: int, top: int) -> None:
    """Backward-compatible normal source-over reference."""
    blend_over(base, overlay, left, top, mode="normal")


def _features(
    inputs: ComposerFrameInputs,
    binding: str,
    *,
    item_id: str | None = None,
) -> AudioFrameFeatures:
    """Resolve per-item visualizer data before stem/master fallback."""
    if item_id:
        item_features = inputs.audio.get(item_id)
        if item_features is not None:
            return item_features
    return inputs.audio.get(binding, inputs.audio.get("master", AudioFrameFeatures()))


def render_composer_frame(
    base_frame: np.ndarray,
    state: OverlayComposerState,
    inputs: ComposerFrameInputs,
    *,
    visualizer_color: VisualizerColor = VisualizerColor(),
) -> np.ndarray:
    canvas = _validate_base(base_frame)
    height, width = canvas.shape[:2]
    for item in state.ordered():
        if item.media is not None:
            source = inputs.media_rgba.get(item.id)
            if source is None:
                # Media selection/playback can legitimately mark a layer inactive.
                continue
            features = _features(inputs, item.media.audio_binding)
            frame_state = evaluate_media_frame(
                item.media,
                time_seconds=inputs.project_time,
                rms=features.rms,
                onset=features.onset,
            )
            transformed, left, top = transform_overlay(
                source,
                frame_state,
                width,
                height,
            )
            blend_over(
                canvas,
                transformed,
                left,
                top,
                mode=item.media.blend,
            )
            continue

        layer = item.visualizer
        assert layer is not None
        features = _features(inputs, layer.binding, item_id=item.id)
        frame_state = evaluate_visualizer_frame(
            layer,
            time_seconds=inputs.project_time,
            rms=features.rms,
            onset=features.onset,
            band_energy=features.band_energy,
        )
        values = (
            features.values
            if features.values
            else tuple(0.0 for _ in range(max(8, layer.bars)))
        )
        overlay = render_visualizer_rgba(
            layer,
            values,
            frame_state,
            width=width,
            height=height,
            color=visualizer_color,
        )
        # Reference visualizer renderer already applies x/y/scale; only normal
        # alpha-over remains until visualizers receive their own blend contract.
        alpha_over(canvas, overlay, 0, 0)
    return canvas
