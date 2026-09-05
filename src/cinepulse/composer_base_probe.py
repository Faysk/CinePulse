from __future__ import annotations

"""Probe the exact base-video contract used by Preview Composer reference export."""

import json
import os
from pathlib import Path
import subprocess

from .composer_export import ComposerBaseProfile

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _rate(value: object) -> float:
    text = str(value or "").strip()
    if not text or text in {"0/0", "N/A"}:
        return 0.0
    try:
        if "/" in text:
            left, right = text.split("/", 1)
            denominator = float(right)
            return float(left) / denominator if denominator else 0.0
        return float(text)
    except ValueError:
        return 0.0


def base_profile_from_probe(payload: object) -> ComposerBaseProfile:
    if not isinstance(payload, dict):
        raise ValueError("base FFprobe payload must be an object")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise ValueError("base FFprobe payload has no streams")
    stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), None)
    if not isinstance(stream, dict):
        raise ValueError("base video stream is missing")
    fmt_value = payload.get("format")
    fmt = fmt_value if isinstance(fmt_value, dict) else {}
    try:
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        duration = float(stream.get("duration") or fmt.get("duration") or 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("base video dimensions/duration are invalid") from exc
    fps = _rate(stream.get("avg_frame_rate")) or _rate(stream.get("r_frame_rate"))
    return ComposerBaseProfile(
        width=width,
        height=height,
        fps=fps,
        duration=duration,
        pixel_format=str(stream.get("pix_fmt") or "unknown"),
        primaries=str(stream.get("color_primaries") or "unknown"),
        transfer=str(stream.get("color_transfer") or "unknown"),
        matrix=str(stream.get("color_space") or "unknown"),
        color_range=str(stream.get("color_range") or "unknown"),
    )


def probe_composer_base(ffprobe: str, source: str | Path, *, timeout: float = 15.0) -> ComposerBaseProfile:
    command = [
        str(ffprobe), "-v", "error", "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_type,width,height,avg_frame_rate,r_frame_rate,pix_fmt,color_primaries,color_transfer,color_space,color_range,duration:format=duration",
        "-of", "json", str(source),
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
        raise RuntimeError(f"could not probe Preview Composer base: {exc}") from exc
    if result.returncode:
        raise RuntimeError((result.stderr or "").strip() or "FFprobe could not inspect Composer base")
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("FFprobe returned invalid Composer base JSON") from exc
    return base_profile_from_probe(payload)
