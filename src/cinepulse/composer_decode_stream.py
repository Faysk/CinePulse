from __future__ import annotations

"""Bounded sequential RGBA decoding for the Preview Composer CPU reference.

The original correctness path launched one FFmpeg process for every media layer
on every output frame and selected ``n == frame_index``.  That is exact, but it
turns an otherwise streaming export into thousands of process launches.

This module preserves frame-index semantics while keeping at most one lazy
FFmpeg decoder per media layer.  Requests that move forward consume the stream,
repeated frame indices reuse the last immutable frame, and a loop/back-seek
restarts the decoder from frame zero.  The CPU reference therefore keeps the
same decoded-frame contract without approximate timestamp seeking.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable, Mapping

import numpy as np

from .composer_decode import MAX_REFERENCE_PIXELS
from .composer_media import ComposerMediaInfo, ComposerPlaybackPosition
from .gpu_compositor import OverlayLayer
from .process_control import popen_group_kwargs, terminate_process_tree

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def build_sequential_rgba_command(
    ffmpeg: str,
    layer: OverlayLayer,
    info: ComposerMediaInfo,
) -> list[str]:
    if Path(layer.source) != Path(info.source):
        raise ValueError("composer stream decode asset does not match layer source")
    pixels = int(info.width) * int(info.height)
    if pixels <= 0 or pixels > MAX_REFERENCE_PIXELS:
        raise ValueError("composer stream decode dimensions are outside safe bounds")
    return [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-i",
        str(layer.source),
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-fps_mode",
        "passthrough",
        "-pix_fmt",
        "rgba",
        "-f",
        "rawvideo",
        "pipe:1",
    ]


def _read_exact(stream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = int(size)
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


@dataclass(frozen=True)
class DecoderPoolStats:
    process_starts: int
    frames_read: int
    cache_hits: int
    restarts: int


class SequentialRgbaDecoder:
    """One lazy exact-order FFmpeg decoder for one media layer."""

    def __init__(
        self,
        ffmpeg: str,
        layer: OverlayLayer,
        info: ComposerMediaInfo,
        *,
        log: Callable[[str], None] | None = None,
        process_factory: Callable[..., subprocess.Popen] | None = None,
    ) -> None:
        # Validate the immutable layer/info pair immediately rather than only
        # when the first output frame happens to use it.
        build_sequential_rgba_command(ffmpeg, layer, info)
        self.ffmpeg = str(ffmpeg)
        self.layer = layer
        self.info = info
        self.log = log or (lambda _message: None)
        self._process_factory = process_factory or subprocess.Popen
        self._process: subprocess.Popen | None = None
        self._stderr = None
        self._next_index = 0
        self._cached_index: int | None = None
        self._cached_frame: np.ndarray | None = None
        self._starts = 0
        self._frames_read = 0
        self._cache_hits = 0
        self._restarts = 0

    @property
    def frame_bytes(self) -> int:
        return int(self.info.width) * int(self.info.height) * 4

    @property
    def stats(self) -> DecoderPoolStats:
        return DecoderPoolStats(self._starts, self._frames_read, self._cache_hits, self._restarts)

    def _stderr_tail(self) -> str:
        stream = self._stderr
        if stream is None:
            return ""
        try:
            stream.flush()
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            stream.seek(max(0, end - 4000), os.SEEK_SET)
            return stream.read().decode("utf-8", errors="replace").strip()
        except (OSError, ValueError, AttributeError):
            return ""

    def _spawn(self) -> None:
        if self._process is not None:
            return
        self._stderr = tempfile.TemporaryFile(mode="w+b")
        try:
            self._process = self._process_factory(
                build_sequential_rgba_command(self.ffmpeg, self.layer, self.info),
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                stdin=subprocess.DEVNULL,
                **popen_group_kwargs(),
            )
        except BaseException:
            self._stderr.close()
            self._stderr = None
            raise
        if self._process.stdout is None:
            self.close()
            raise RuntimeError("composer stream decoder has no stdout pipe")
        self._next_index = 0
        self._starts += 1

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        if process is not None:
            terminate_process_tree(process, self.log, grace_seconds=1.0)
            try:
                if process.stdout is not None and not process.stdout.closed:
                    process.stdout.close()
            except OSError:
                pass
        if self._stderr is not None:
            try:
                self._stderr.close()
            except OSError:
                pass
            self._stderr = None
        self._next_index = 0

    def _restart(self) -> None:
        self._stop_process()
        self._cached_index = None
        self._cached_frame = None
        self._restarts += 1

    def frame(self, position: ComposerPlaybackPosition) -> np.ndarray | None:
        if not position.active:
            return None
        target = int(position.frame_index)
        if not 0 <= target < int(self.info.frame_count):
            raise ValueError("composer stream playback frame index is outside media bounds")

        if self._cached_index == target and self._cached_frame is not None:
            self._cache_hits += 1
            return self._cached_frame

        # A lower target means loop wrap or explicit back-seek. Sequential raw
        # decode cannot move backwards, so restart from frame zero exactly.
        if self._process is not None and target < self._next_index:
            self._restart()

        self._spawn()
        assert self._process is not None and self._process.stdout is not None
        while self._next_index <= target:
            raw = _read_exact(self._process.stdout, self.frame_bytes)
            if len(raw) != self.frame_bytes:
                details = self._stderr_tail()
                code = self._process.poll()
                suffix = f"; decoder exited with {code}" if code is not None else ""
                raise RuntimeError(
                    details or
                    f"composer stream decoder produced {len(raw)}/{self.frame_bytes} bytes "
                    f"at media frame {self._next_index}{suffix}"
                )
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.info.height, self.info.width, 4).copy()
            # Callers must not mutate the shared cache; the reference compositor
            # treats layer pixels as source-only and copies before transforms.
            frame.setflags(write=False)
            self._cached_frame = frame
            self._cached_index = self._next_index
            self._next_index += 1
            self._frames_read += 1

        assert self._cached_frame is not None and self._cached_index == target
        # Static media no longer need a live FFmpeg process after frame zero.
        if self.info.frame_count == 1 and not self.info.animated:
            cached = self._cached_frame
            self._stop_process()
            self._cached_frame = cached
            self._cached_index = 0
        return self._cached_frame

    def close(self) -> None:
        self._stop_process()
        self._cached_frame = None
        self._cached_index = None

    def __enter__(self) -> "SequentialRgbaDecoder":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()


class ComposerMediaDecoderPool:
    """Lazy per-item decoder pool with one cached RGBA frame per active layer."""

    def __init__(
        self,
        ffmpeg: str,
        layers: Mapping[str, tuple[OverlayLayer, ComposerMediaInfo]],
        *,
        log: Callable[[str], None] | None = None,
        process_factory: Callable[..., subprocess.Popen] | None = None,
    ) -> None:
        self._decoders = {
            str(item_id): SequentialRgbaDecoder(
                ffmpeg,
                layer,
                info,
                log=log,
                process_factory=process_factory,
            )
            for item_id, (layer, info) in layers.items()
        }

    def frame(self, item_id: str, position: ComposerPlaybackPosition) -> np.ndarray | None:
        try:
            decoder = self._decoders[str(item_id)]
        except KeyError as exc:
            raise KeyError(f"composer decoder pool has no media layer {item_id}") from exc
        return decoder.frame(position)

    @property
    def stats(self) -> DecoderPoolStats:
        starts = frames = hits = restarts = 0
        for decoder in self._decoders.values():
            value = decoder.stats
            starts += value.process_starts
            frames += value.frames_read
            hits += value.cache_hits
            restarts += value.restarts
        return DecoderPoolStats(starts, frames, hits, restarts)

    def close(self) -> None:
        for decoder in self._decoders.values():
            decoder.close()

    def __enter__(self) -> "ComposerMediaDecoderPool":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()
