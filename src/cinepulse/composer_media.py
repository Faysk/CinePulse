from __future__ import annotations

"""Preview-only media probing and deterministic playback for Overlay Composer.

The composer accepts still/animated images and alpha-capable video, but the
render path must not guess timing or transparency from a filename. This module
turns FFprobe metadata into a small backend-neutral contract that preview, CPU
rendering and any future evidence-gated GPU compositor can share.

It is intentionally isolated from Stable RenderSettings.
"""

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Iterable

from .gpu_compositor import OverlayLayer

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_ALPHA_PREFIXES = (
    "rgba",
    "bgra",
    "argb",
    "abgr",
    "yuva",
    "gbrap",
    "ya",
)


@dataclass(frozen=True)
class ComposerMediaInfo:
    source: str
    width: int
    height: int
    fps: float
    duration: float
    frame_count: int
    pixel_format: str
    codec: str
    has_alpha: bool
    animated: bool

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("composer media dimensions must be positive")
        if self.fps <= 0:
            raise ValueError("composer media fps must be positive")
        if self.duration <= 0:
            raise ValueError("composer media duration must be positive")
        if self.frame_count <= 0:
            raise ValueError("composer media frame count must be positive")


@dataclass(frozen=True)
class ComposerPlaybackPosition:
    active: bool
    local_time: float
    frame_index: int
    loop_index: int


def _parse_rate(value: object) -> float:
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return 0.0
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            den = float(denominator)
            return float(numerator) / den if den else 0.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _parse_float(*values: object) -> float:
    for value in values:
        try:
            parsed = float(str(value))
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed) and parsed > 0:
            return parsed
    return 0.0


def _parse_int(*values: object) -> int:
    for value in values:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0


def pixel_format_has_alpha(pixel_format: str) -> bool:
    value = str(pixel_format or "").strip().lower()
    return any(value.startswith(prefix) for prefix in _ALPHA_PREFIXES)


def media_info_from_probe(source: str | Path, payload: object) -> ComposerMediaInfo:
    """Build a conservative media contract from FFprobe JSON output.

    Some animated-image demuxers omit ``nb_frames`` even when duration and a
    reliable frame rate are present. Treating those files as one-frame assets
    makes every playback timestamp resolve to frame zero, so derive the frame
    count from timing when the explicit count is unavailable. Static images do
    not normally expose a positive duration and therefore keep the one-frame
    hold contract.
    """
    if not isinstance(payload, dict):
        raise ValueError("FFprobe payload must be an object")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ValueError("FFprobe payload has no stream list")
    stream = next(
        (item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"),
        None,
    )
    if not isinstance(stream, dict):
        raise ValueError("overlay media has no video stream")

    format_payload = payload.get("format")
    fmt = format_payload if isinstance(format_payload, dict) else {}
    width = _parse_int(stream.get("width"))
    height = _parse_int(stream.get("height"))
    fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(stream.get("r_frame_rate"))
    duration = _parse_float(stream.get("duration"), fmt.get("duration"))
    frames = _parse_int(stream.get("nb_frames"))

    if fps <= 0 and frames > 1 and duration > 0:
        fps = frames / duration
    if duration <= 0 and fps > 0 and frames > 0:
        duration = frames / fps
    if frames <= 0 and fps > 0 and duration > 0:
        # Round rather than floor so 29.97-style metadata does not silently lose
        # the final effective frame because of decimal duration representation.
        frames = max(1, int(round(duration * fps)))

    # Static images commonly report neither duration nor frame rate. Give them
    # a deterministic one-frame timeline without pretending they are animated.
    if frames <= 0:
        frames = 1
    if fps <= 0:
        fps = 1.0
    if duration <= 0:
        duration = max(frames / fps, 1e-6)

    pixel_format = str(stream.get("pix_fmt") or "").strip().lower()
    codec = str(stream.get("codec_name") or "unknown").strip().lower() or "unknown"
    animated = frames > 1 or duration > (1.5 / fps)

    return ComposerMediaInfo(
        source=str(Path(source)),
        width=width,
        height=height,
        fps=float(fps),
        duration=float(duration),
        frame_count=int(frames),
        pixel_format=pixel_format,
        codec=codec,
        has_alpha=pixel_format_has_alpha(pixel_format),
        animated=animated,
    )


def probe_composer_media(ffprobe: str, source: str | Path, *, timeout: float = 15.0) -> ComposerMediaInfo:
    path = Path(source)
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1.0, float(timeout)),
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"could not probe composer media: {exc}") from exc
    if result.returncode:
        details = (result.stderr or "").strip()
        raise RuntimeError(details or "FFprobe could not inspect composer media")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("FFprobe returned invalid JSON for composer media") from exc
    return media_info_from_probe(path, payload)


def validate_layer_media(layer: OverlayLayer, info: ComposerMediaInfo) -> tuple[str, ...]:
    """Return fail-closed compatibility errors for one layer/asset pair."""
    problems: list[str] = []
    if Path(layer.source) != Path(info.source):
        problems.append("probed asset does not match layer source")
    if layer.kind == "video-alpha" and not info.has_alpha:
        problems.append("video-alpha layer has no alpha-capable pixel format")
    if layer.kind in {"gif", "apng", "webp"} and not info.animated:
        problems.append("animated image layer contains only one effective frame")
    return tuple(problems)


def playback_position(
    layer: OverlayLayer,
    info: ComposerMediaInfo,
    *,
    project_time: float,
    start_time: float = 0.0,
) -> ComposerPlaybackPosition:
    """Resolve one project timestamp into the asset timeline.

    Before ``start_time`` the layer is inactive. Looping layers wrap on media
    duration; non-looping layers become inactive immediately after their last
    frame instead of freezing forever. Static PNGs remain active because their
    one-frame duration is treated as a held still.
    """
    t = float(project_time) - max(0.0, float(start_time))
    if t < 0:
        return ComposerPlaybackPosition(False, 0.0, 0, 0)

    is_static = info.frame_count <= 1 and not info.animated
    if is_static:
        return ComposerPlaybackPosition(True, 0.0, 0, 0)

    duration = max(float(info.duration), 1e-9)
    if layer.loop:
        loop_index = max(0, int(math.floor(t / duration)))
        local = t % duration
    else:
        if t >= duration:
            return ComposerPlaybackPosition(False, duration, info.frame_count - 1, 0)
        loop_index = 0
        local = t

    frame = min(info.frame_count - 1, max(0, int(math.floor(local * info.fps + 1e-9))))
    return ComposerPlaybackPosition(True, local, frame, loop_index)


def validate_project_media(
    layers: Iterable[tuple[OverlayLayer, ComposerMediaInfo]],
) -> tuple[str, ...]:
    errors: list[str] = []
    for index, (layer, info) in enumerate(layers):
        for problem in validate_layer_media(layer, info):
            errors.append(f"layer {index}: {problem}")
    return tuple(errors)
