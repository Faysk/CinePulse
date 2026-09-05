from __future__ import annotations

"""Single-frame CPU reference preview for Overlay Composer.

The preview intentionally reuses the same media timing, audio envelopes,
transform/blend math and SDR color conversion contract as final reference
export. The display canvas is bounded independently of final output resolution:
an 8K/12K project therefore previews at an aspect-correct editor size instead
of allocating a full-resolution RGBA base frame.

This remains a random-access CPU correctness path, not a claim that the H6 GPU
route has physical acceptance.
"""

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
from typing import Mapping

import numpy as np

from .composer_audio_binding import composer_audio_features, load_bound_visualizer_envelopes
from .composer_decode import decode_exact_rgba_frame
from .composer_export import ComposerBaseProfile
from .composer_media import playback_position, probe_composer_media, validate_layer_media
from .composer_runtime import ComposerFrameInputs, render_composer_frame
from .gpu_media import CREATE_NO_WINDOW
from .overlay_composer import OverlayComposerState


DEFAULT_PREVIEW_WIDTH = 960
DEFAULT_PREVIEW_HEIGHT = 540


@dataclass(frozen=True)
class ComposerPreviewResult:
    rgba: np.ndarray
    project_time: float
    frame_index: int
    media_layers: int
    visualizers: int
    canvas_width: int
    canvas_height: int
    resolution_scale: float


def fit_preview_canvas(
    width: int,
    height: int,
    *,
    max_width: int = DEFAULT_PREVIEW_WIDTH,
    max_height: int = DEFAULT_PREVIEW_HEIGHT,
) -> tuple[int, int, float]:
    """Fit a final canvas into a bounded editor canvas without upscaling."""
    source_w = int(width)
    source_h = int(height)
    bound_w = int(max_width)
    bound_h = int(max_height)
    if source_w <= 0 or source_h <= 0 or bound_w <= 0 or bound_h <= 0:
        raise ValueError("composer preview dimensions must be positive")
    scale = min(1.0, bound_w / source_w, bound_h / source_h)
    target_w = max(1, int(round(source_w * scale)))
    target_h = max(1, int(round(source_h * scale)))
    # Rounding can overshoot a bound by one on awkward aspect ratios.
    target_w = min(bound_w, target_w)
    target_h = min(bound_h, target_h)
    effective_scale = min(target_w / source_w, target_h / source_h)
    return target_w, target_h, float(effective_scale)


def _range_token(value: str) -> str:
    return "pc" if str(value).strip().lower() in {"pc", "jpeg", "full"} else "tv"


def _base_preview_command(
    ffmpeg: str,
    source: str | Path,
    profile: ComposerBaseProfile,
    frame_index: int,
    *,
    target_width: int | None = None,
    target_height: int | None = None,
) -> list[str]:
    index = max(0, int(frame_index))
    width = int(target_width if target_width is not None else profile.width)
    height = int(target_height if target_height is not None else profile.height)
    if width <= 0 or height <= 0:
        raise ValueError("composer preview target dimensions must be positive")
    select = f"select=eq(n\\,{index})"
    convert = (
        f"scale=w={width}:h={height}:in_color_matrix=bt709:out_color_matrix=bt709:"
        f"in_range={_range_token(profile.color_range)}:out_range=pc"
    )
    return [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-vf",
        f"{select},{convert},format=rgba",
        "-frames:v",
        "1",
        "-fps_mode",
        "passthrough",
        "-pix_fmt",
        "rgba",
        "-f",
        "rawvideo",
        "pipe:1",
    ]


def _decode_base_frame(
    ffmpeg: str,
    source: str | Path,
    profile: ComposerBaseProfile,
    frame_index: int,
    *,
    target_width: int,
    target_height: int,
    timeout: float = 60.0,
) -> np.ndarray:
    try:
        result = subprocess.run(
            _base_preview_command(
                ffmpeg,
                source,
                profile,
                frame_index,
                target_width=target_width,
                target_height=target_height,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1.0, float(timeout)),
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"composer preview base decode failed: {exc}") from exc
    if result.returncode:
        details = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(details or f"composer preview base decode exited with {result.returncode}")
    expected = int(target_width) * int(target_height) * 4
    if len(result.stdout) != expected:
        raise RuntimeError(
            f"composer preview base decode produced {len(result.stdout)} bytes; expected {expected}"
        )
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(
        int(target_height),
        int(target_width),
        4,
    ).copy()


def render_composer_preview(
    *,
    source: str | Path,
    profile: ComposerBaseProfile,
    state: OverlayComposerState,
    ffmpeg: str,
    ffprobe: str,
    project_time: float,
    audio_sources: Mapping[str, str | Path] | None = None,
    max_width: int = DEFAULT_PREVIEW_WIDTH,
    max_height: int = DEFAULT_PREVIEW_HEIGHT,
) -> ComposerPreviewResult:
    """Render one bounded editor frame through the CPU reference contract."""
    if not profile.reference_supported:
        raise ValueError("Preview Composer still preview currently accepts only 8-bit SDR BT.709")
    ordered = state.ordered()
    if not ordered:
        raise ValueError("Preview Composer has no enabled layers to preview")

    canvas_w, canvas_h, resolution_scale = fit_preview_canvas(
        profile.width,
        profile.height,
        max_width=max_width,
        max_height=max_height,
    )
    frame_count = max(1, int(round(profile.duration * profile.fps)))
    requested_time = max(
        0.0,
        min(float(project_time), max(0.0, profile.duration - 1e-9)),
    )
    frame_index = min(
        frame_count - 1,
        max(0, int(math.floor(requested_time * profile.fps + 1e-9))),
    )
    actual_time = frame_index / profile.fps
    base = _decode_base_frame(
        ffmpeg,
        source,
        profile,
        frame_index,
        target_width=canvas_w,
        target_height=canvas_h,
    )

    media_frames: dict[str, np.ndarray] = {}
    media_count = 0
    visualizer_count = 0
    for item in ordered:
        if item.media is None:
            visualizer_count += 1
            continue
        media_count += 1
        info = probe_composer_media(ffprobe, item.media.source, exact_timing=True)
        problems = validate_layer_media(item.media, info)
        if problems:
            raise ValueError(f"composer media {item.id}: " + "; ".join(problems))
        position = playback_position(item.media, info, project_time=actual_time)
        decoded = decode_exact_rgba_frame(ffmpeg, item.media, info, position)
        if decoded is not None:
            media_frames[item.id] = decoded

    sources = dict(audio_sources or {})
    if "master" not in sources:
        sources["master"] = source
    envelopes = load_bound_visualizer_envelopes(
        state,
        ffmpeg=ffmpeg,
        sources=sources,
        duration=profile.duration,
    )
    audio = composer_audio_features(state, envelopes, project_time=actual_time)
    rendered = render_composer_frame(
        base,
        state,
        ComposerFrameInputs(actual_time, media_frames, audio),
        media_resolution_scale=resolution_scale,
    )
    return ComposerPreviewResult(
        rgba=rendered,
        project_time=actual_time,
        frame_index=frame_index,
        media_layers=media_count,
        visualizers=visualizer_count,
        canvas_width=canvas_w,
        canvas_height=canvas_h,
        resolution_scale=resolution_scale,
    )
