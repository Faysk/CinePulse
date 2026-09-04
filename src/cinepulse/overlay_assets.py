from __future__ import annotations

import json
import math
import os
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class OverlayAssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class AssetProbe:
    path: str
    width: int
    height: int
    duration: float
    fps: float
    animated: bool
    has_alpha: bool
    codec: str


@dataclass(frozen=True)
class AssetFrameKey:
    path: str
    mtime_ns: int
    size: int
    width: int
    height: int
    time_bucket_ms: int
    preserve_aspect: bool


class AssetFrameCache:
    """Small bounded in-memory cache used by interactive preview only."""

    def __init__(self, max_entries: int = 48) -> None:
        self.max_entries = max(1, int(max_entries))
        self._frames: OrderedDict[AssetFrameKey, np.ndarray] = OrderedDict()

    def get(self, key: AssetFrameKey) -> np.ndarray | None:
        frame = self._frames.get(key)
        if frame is None:
            return None
        self._frames.move_to_end(key)
        return frame.copy()

    def put(self, key: AssetFrameKey, frame: np.ndarray) -> None:
        self._frames[key] = frame.copy()
        self._frames.move_to_end(key)
        while len(self._frames) > self.max_entries:
            self._frames.popitem(last=False)

    def clear(self) -> None:
        self._frames.clear()


def _parse_fraction(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            denominator = float(right)
            return float(left) / denominator if denominator else 0.0
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def probe_asset(ffprobe: str, path: str, *, timeout: float = 8.0) -> AssetProbe:
    source = Path(path)
    if not source.is_file():
        raise OverlayAssetError(f"Asset não encontrado: {path}")
    command = [
        str(ffprobe), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,pix_fmt,avg_frame_rate,nb_frames,duration:format=duration",
        "-of", "json", str(source),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OverlayAssetError(f"Não foi possível inspecionar o asset: {path}") from exc
    if result.returncode:
        raise OverlayAssetError(result.stderr.strip() or f"FFprobe falhou para {path}")
    try:
        payload = json.loads(result.stdout)
        stream = payload.get("streams", [])[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        raise OverlayAssetError("FFprobe retornou metadados inválidos para o asset.") from exc
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise OverlayAssetError("Asset não possui dimensões de vídeo válidas.")
    duration_values = [stream.get("duration"), payload.get("format", {}).get("duration")]
    duration = 0.0
    for value in duration_values:
        try:
            duration = max(duration, float(value or 0.0))
        except (TypeError, ValueError):
            pass
    fps = _parse_fraction(stream.get("avg_frame_rate"))
    try:
        frame_count = int(stream.get("nb_frames") or 0)
    except (TypeError, ValueError):
        frame_count = 0
    suffix = source.suffix.lower()
    animated = suffix == ".gif" and (frame_count > 1 or duration > 0.0 or fps > 0.0)
    pix_fmt = str(stream.get("pix_fmt") or "").lower()
    has_alpha = "a" in pix_fmt or suffix in {".png", ".gif"}
    return AssetProbe(
        path=str(source), width=width, height=height, duration=max(0.0, duration),
        fps=max(0.0, fps), animated=animated, has_alpha=has_alpha,
        codec=str(stream.get("codec_name") or "unknown"),
    )


def effective_asset_time(timeline_seconds: float, *, duration: float, speed: float = 1.0, loop: bool = True) -> float:
    timeline = max(0.0, float(timeline_seconds))
    speed = float(speed)
    if not math.isfinite(speed) or speed <= 0:
        raise OverlayAssetError("Velocidade do asset precisa ser positiva.")
    value = timeline * speed
    if duration > 0:
        if loop:
            value = value % duration
        else:
            value = min(value, max(0.0, duration - 0.001))
    return max(0.0, value)


def _frame_key(path: Path, width: int, height: int, seconds: float, preserve_aspect: bool) -> AssetFrameKey:
    stat = path.stat()
    return AssetFrameKey(
        path=str(path.resolve()), mtime_ns=stat.st_mtime_ns, size=stat.st_size,
        width=int(width), height=int(height), time_bucket_ms=max(0, int(round(seconds * 1000.0))),
        preserve_aspect=bool(preserve_aspect),
    )


def decode_asset_rgba(
    ffmpeg: str,
    path: str,
    *,
    width: int,
    height: int,
    timeline_seconds: float = 0.0,
    duration: float = 0.0,
    speed: float = 1.0,
    loop: bool = True,
    preserve_aspect: bool = True,
    cache: AssetFrameCache | None = None,
    timeout: float = 10.0,
) -> np.ndarray:
    source = Path(path)
    if not source.is_file():
        raise OverlayAssetError(f"Asset não encontrado: {path}")
    width = max(1, int(width))
    height = max(1, int(height))
    seconds = effective_asset_time(timeline_seconds, duration=duration, speed=speed, loop=loop)
    key = _frame_key(source, width, height, seconds, preserve_aspect)
    if cache is not None:
        existing = cache.get(key)
        if existing is not None:
            return existing

    if preserve_aspect:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x00000000,format=rgba"
        )
    else:
        vf = f"scale={width}:{height}:flags=lanczos,format=rgba"
    command = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-ss", f"{seconds:.6f}",
        "-i", str(source), "-frames:v", "1", "-vf", vf,
        "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OverlayAssetError(f"Não foi possível decodificar {source.name}.") from exc
    expected = width * height * 4
    if result.returncode or len(result.stdout) != expected:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise OverlayAssetError(stderr or f"Frame RGBA incompleto para {source.name}.")
    frame = np.frombuffer(result.stdout, dtype=np.uint8).reshape(height, width, 4).copy()
    if cache is not None:
        cache.put(key, frame)
    return frame
