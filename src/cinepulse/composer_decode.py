from __future__ import annotations

"""Exact CPU-reference media decoding for Preview Overlay Composer.

Animated assets are selected by decoded frame index rather than approximate
seek timestamps. This is intentionally conservative and may be slower than a
GPU decoder; H6 optimization is only allowed to replace it after pixel/timing
parity is physically demonstrated.
"""

import os
from pathlib import Path
import subprocess

import numpy as np

from .composer_media import ComposerMediaInfo, ComposerPlaybackPosition
from .gpu_compositor import OverlayLayer

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
MAX_REFERENCE_PIXELS = 16384 * 16384


def build_exact_rgba_command(
    ffmpeg: str,
    layer: OverlayLayer,
    info: ComposerMediaInfo,
    position: ComposerPlaybackPosition,
) -> list[str]:
    if Path(layer.source) != Path(info.source):
        raise ValueError("composer decode asset does not match layer source")
    if not position.active:
        raise ValueError("cannot decode an inactive composer playback position")
    if not 0 <= int(position.frame_index) < int(info.frame_count):
        raise ValueError("composer playback frame index is outside media bounds")
    pixels = int(info.width) * int(info.height)
    if pixels <= 0 or pixels > MAX_REFERENCE_PIXELS:
        raise ValueError("composer reference decode dimensions are outside safe bounds")

    # select=n is slower than timestamp seeking but exact for the CPU reference.
    # Escaping the comma keeps the filter portable through FFmpeg's parser.
    # `-vsync 0` was deprecated and is no longer accepted by FFmpeg 9 on the
    # Windows release runner. `-fps_mode passthrough` is the modern per-stream
    # equivalent and, critically, still prevents implicit duplication/drop.
    select = f"select=eq(n\\,{int(position.frame_index)}),format=rgba"
    return [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(layer.source),
        "-vf",
        select,
        "-fps_mode",
        "passthrough",
        "-frames:v",
        "1",
        "-pix_fmt",
        "rgba",
        "-f",
        "rawvideo",
        "pipe:1",
    ]


def decode_exact_rgba_frame(
    ffmpeg: str,
    layer: OverlayLayer,
    info: ComposerMediaInfo,
    position: ComposerPlaybackPosition,
    *,
    timeout: float = 30.0,
) -> np.ndarray | None:
    if not position.active:
        return None
    command = build_exact_rgba_command(ffmpeg, layer, info, position)
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1.0, float(timeout)),
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"composer reference decode failed: {exc}") from exc
    if result.returncode:
        details = (result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(details or f"composer reference decode exited with {result.returncode}")
    expected = int(info.width) * int(info.height) * 4
    if len(result.stdout) != expected:
        raise RuntimeError(
            f"composer reference decode produced {len(result.stdout)} bytes; expected {expected}"
        )
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(info.height, info.width, 4).copy()
