from __future__ import annotations

"""Single-frame CPU reference preview for Overlay Composer.

The preview intentionally reuses the same media timing, audio envelopes,
transform/blend math and SDR color conversion contract as final reference
export. It is a bounded random-access correctness path for the editor, not a
claim that the H6 GPU route has physical acceptance.
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


@dataclass(frozen=True)
class ComposerPreviewResult:
    rgba: np.ndarray
    project_time: float
    frame_index: int
    media_layers: int
    visualizers: int


def _range_token(value: str) -> str:
    return "pc" if str(value).strip().lower() in {"pc", "jpeg", "full"} else "tv"


def _base_preview_command(
    ffmpeg: str,
    source: str | Path,
    profile: ComposerBaseProfile,
    frame_index: int,
) -> list[str]:
    index = max(0, int(frame_index))
    select = f"select=eq(n\\,{index})"
    convert = (
        f"scale=w=iw:h=ih:in_color_matrix=bt709:out_color_matrix=bt709:"
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
    timeout: float = 60.0,
) -> np.ndarray:
    result = subprocess.run(
        _base_preview_command(ffmpeg, source, profile, frame_index),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(1.0, float(timeout)),
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode:
        details = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(details or f"composer preview base decode exited with {result.returncode}")
    expected = int(profile.width) * int(profile.height) * 4
    if len(result.stdout) != expected:
        raise RuntimeError(
            f"composer preview base decode produced {len(result.stdout)} bytes; expected {expected}"
        )
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(
        int(profile.height),
        int(profile.width),
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
) -> ComposerPreviewResult:
    """Render one editor preview frame through the CPU reference contract."""
    if not profile.reference_supported:
        raise ValueError("Preview Composer still preview currently accepts only 8-bit SDR BT.709")
    ordered = state.ordered()
    if not ordered:
        raise ValueError("Preview Composer has no enabled layers to preview")

    frame_count = max(1, int(round(profile.duration * profile.fps)))
    requested_time = max(0.0, min(float(project_time), max(0.0, profile.duration - 1e-9)))
    frame_index = min(
        frame_count - 1,
        max(0, int(math.floor(requested_time * profile.fps + 1e-9))),
    )
    actual_time = frame_index / profile.fps
    base = _decode_base_frame(ffmpeg, source, profile, frame_index)

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
    )
    return ComposerPreviewResult(
        rgba=rendered,
        project_time=actual_time,
        frame_index=frame_index,
        media_layers=media_count,
        visualizers=visualizer_count,
    )
