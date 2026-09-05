from __future__ import annotations

"""Bounded, cancellable CPU-reference export for Preview Overlay Composer.

This is deliberately a correctness path, not the H6 fast path. It streams one
base frame at a time, keeps at most one decoded RGBA frame per enabled media
layer, applies the deterministic CPU reference compositor, writes a lossless
FFV1 RGB master, then atomically promotes the muxed result. Media assets use a
bounded sequential decoder pool: forward playback consumes exact frame order,
repeated frames reuse the immutable last frame, and loop/back-seek restarts from
frame zero instead of using approximate timestamp seeking.

GPU routes may only replace stages after their exact visual/timing/color
evidence is approved. For now the reference export is intentionally limited to
8-bit SDR BT.709. HDR/10-bit sources fail closed instead of being silently
converted by a Preview feature whose HDR parity has not been proven.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable, Mapping

import numpy as np

from .composer_audio import VisualizerAudioEnvelope
from .composer_audio_binding import composer_audio_features, load_bound_visualizer_envelopes
from .composer_decode_stream import ComposerMediaDecoderPool
from .composer_media import ComposerMediaInfo, playback_position, probe_composer_media, validate_layer_media
from .composer_runtime import ComposerFrameInputs, render_composer_frame
from .overlay_composer import OverlayComposerState
from .process_control import popen_group_kwargs, terminate_process_tree
from .safe_output import AtomicOutput


@dataclass(frozen=True)
class ComposerBaseProfile:
    width: int
    height: int
    fps: float
    duration: float
    pixel_format: str
    primaries: str
    transfer: str
    matrix: str
    color_range: str

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.fps <= 0 or self.duration <= 0:
            raise ValueError("composer base dimensions/timing must be positive")

    @property
    def reference_supported(self) -> bool:
        pix = self.pixel_format.strip().lower()
        transfer = self.transfer.strip().lower()
        primaries = self.primaries.strip().lower()
        matrix = self.matrix.strip().lower()
        return (
            not any(token in pix for token in ("10", "12", "16", "p010", "p016"))
            and transfer in {"bt709", "iec61966-2-1", "unknown", ""}
            and primaries in {"bt709", "unknown", ""}
            and matrix in {"bt709", "unknown", ""}
        )


@dataclass(frozen=True)
class ComposerExportRequest:
    source: Path
    output: Path
    profile: ComposerBaseProfile
    state: OverlayComposerState
    ffmpeg: str
    ffprobe: str
    audio_sources: Mapping[str, str | Path]


@dataclass(frozen=True)
class ComposerExportResult:
    output: Path
    frames: int
    duration: float
    used_media_layers: int
    used_visualizers: int


def _range_token(value: str) -> str:
    return "pc" if str(value).strip().lower() in {"pc", "jpeg", "full"} else "tv"


def _base_decode_command(request: ComposerExportRequest, frames: int) -> list[str]:
    p = request.profile
    range_in = _range_token(p.color_range)
    # The reference accepts only BT.709 SDR, so no gamut/transfer conversion is
    # required here. What must be explicit is the YUV->RGB matrix and range.
    # swscale's scale filter owns that conversion directly and is portable across
    # FFmpeg 6-9; newer zscale builds can reject matrix=gbr while negotiating a
    # YUV output family before a following format=rgba filter (zimg code 1026).
    # Keeping w/h unchanged makes this a pure color-family/range conversion.
    vf = (
        f"scale=w=iw:h=ih:in_color_matrix=bt709:out_color_matrix=bt709:"
        f"in_range={range_in}:out_range=pc,format=rgba"
    )
    return [
        str(request.ffmpeg), "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", str(request.source), "-map", "0:v:0", "-an", "-sn",
        "-vf", vf, "-fps_mode", "passthrough", "-frames:v", str(frames),
        "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1",
    ]


def _video_encode_command(request: ComposerExportRequest, target: Path) -> list[str]:
    p = request.profile
    return [
        str(request.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s:v", f"{p.width}x{p.height}",
        "-r", f"{p.fps:.12g}", "-i", "pipe:0", "-an",
        "-c:v", "ffv1", "-level", "3", "-pix_fmt", "gbrap",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "gbr",
        str(target),
    ]


def _mux_command(request: ComposerExportRequest, visual: Path, target: Path) -> list[str]:
    master = request.audio_sources.get("master")
    command = [str(request.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(visual)]
    if master:
        command += ["-i", str(master), "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "copy", "-shortest"]
    else:
        command += ["-map", "0:v:0", "-c:v", "copy"]
    command.append(str(target))
    return command


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


def _validate_media(request: ComposerExportRequest) -> dict[str, ComposerMediaInfo]:
    infos: dict[str, ComposerMediaInfo] = {}
    for item in request.state.ordered():
        if item.media is None:
            continue
        info = probe_composer_media(request.ffprobe, item.media.source)
        problems = validate_layer_media(item.media, info)
        if problems:
            raise ValueError(f"composer media {item.id}: " + "; ".join(problems))
        infos[item.id] = info
    return infos


def export_composer_reference(
    request: ComposerExportRequest,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
    log: Callable[[str], None] | None = None,
    envelopes: Mapping[str, VisualizerAudioEnvelope] | None = None,
) -> ComposerExportResult:
    """Render one Preview Composer project through the lossless CPU reference."""
    cancel = cancelled or (lambda: False)
    logger = log or (lambda _message: None)
    ordered_items = request.state.ordered()
    if not request.profile.reference_supported:
        raise ValueError("Preview Composer CPU reference currently accepts only 8-bit SDR BT.709")
    if not ordered_items:
        raise ValueError("Preview Composer has no enabled layers to export")

    # Validate source assets and build all read-only analysis state before an
    # output partial is prepared. Validation failures therefore cannot leave a
    # new partial file beside a previously good destination.
    frame_count = max(1, int(round(request.profile.duration * request.profile.fps)))
    frame_bytes = request.profile.width * request.profile.height * 4
    media_info = _validate_media(request)
    visualizer_count = sum(1 for item in ordered_items if item.visualizer is not None)
    media_count = len(media_info)

    if envelopes is None:
        envelopes = load_bound_visualizer_envelopes(
            request.state,
            ffmpeg=request.ffmpeg,
            sources=request.audio_sources,
            duration=request.profile.duration,
            log=logger,
        )

    media_layers = {
        item.id: (item.media, media_info[item.id])
        for item in ordered_items
        if item.media is not None
    }
    media_pool = ComposerMediaDecoderPool(request.ffmpeg, media_layers, log=logger)

    output = AtomicOutput.for_path(request.output)
    output.prepare()
    decoder: subprocess.Popen | None = None
    encoder: subprocess.Popen | None = None
    temporary_dir = Path(tempfile.mkdtemp(prefix="cinepulse-composer-", dir=request.output.parent))
    visual_master = temporary_dir / "composer-reference.mkv"
    decoder_log = temporary_dir / "decode.log"
    encoder_log = temporary_dir / "encode.log"
    try:
        with decoder_log.open("wb") as decode_stderr, encoder_log.open("wb") as encode_stderr:
            decoder = subprocess.Popen(
                _base_decode_command(request, frame_count),
                stdout=subprocess.PIPE,
                stderr=decode_stderr,
                stdin=subprocess.DEVNULL,
                **popen_group_kwargs(),
            )
            encoder = subprocess.Popen(
                _video_encode_command(request, visual_master),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=encode_stderr,
                **popen_group_kwargs(),
            )
            assert decoder.stdout is not None and encoder.stdin is not None
            for index in range(frame_count):
                if cancel():
                    raise InterruptedError("Preview Composer export cancelled")
                raw = _read_exact(decoder.stdout, frame_bytes)
                if len(raw) != frame_bytes:
                    decode_stderr.flush()
                    code = decoder.poll()
                    details = decoder_log.read_text(encoding="utf-8", errors="replace")[-4000:]
                    suffix = f"; decoder exited with {code}" if code is not None else ""
                    raise RuntimeError(
                        (details.strip() + suffix) if details.strip() else
                        f"base decoder produced {len(raw)}/{frame_bytes} bytes at frame {index}{suffix}"
                    )
                base = np.frombuffer(raw, dtype=np.uint8).reshape(request.profile.height, request.profile.width, 4)
                project_time = index / request.profile.fps
                media_frames: dict[str, np.ndarray] = {}
                for item in ordered_items:
                    if item.media is None:
                        continue
                    info = media_info[item.id]
                    position = playback_position(item.media, info, project_time=project_time)
                    decoded = media_pool.frame(item.id, position)
                    if decoded is not None:
                        media_frames[item.id] = decoded
                audio = composer_audio_features(request.state, envelopes, project_time=project_time)
                rendered = render_composer_frame(
                    base,
                    request.state,
                    ComposerFrameInputs(project_time, media_frames, audio),
                )
                try:
                    encoder.stdin.write(rendered.tobytes(order="C"))
                except (BrokenPipeError, OSError) as exc:
                    raise RuntimeError("composer reference encoder closed early") from exc
                if progress:
                    progress(index + 1, frame_count)
            encoder.stdin.close()
            decoder.stdout.close()

        decoder_code = decoder.wait(timeout=30)
        encoder_code = encoder.wait(timeout=60)
        if decoder_code:
            details = decoder_log.read_text(encoding="utf-8", errors="replace")[-4000:]
            raise RuntimeError(details.strip() or f"composer base decoder exited with {decoder_code}")
        if encoder_code or not visual_master.is_file() or visual_master.stat().st_size == 0:
            details = encoder_log.read_text(encoding="utf-8", errors="replace")[-4000:]
            raise RuntimeError(details.strip() or f"composer reference encoder exited with {encoder_code}")
        if cancel():
            raise InterruptedError("Preview Composer export cancelled")

        stats = media_pool.stats
        if media_count:
            logger(
                "Composer media decode: "
                f"{stats.process_starts} processo(s), {stats.frames_read} frame(s), "
                f"{stats.cache_hits} cache hit(s), {stats.restarts} restart(s)."
            )

        mux = subprocess.run(
            _mux_command(request, visual_master, output.partial),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if mux.returncode:
            details = (mux.stderr or b"").decode("utf-8", errors="replace")[-4000:]
            raise RuntimeError(details.strip() or f"composer mux exited with {mux.returncode}")
        output.commit()
        return ComposerExportResult(output.final, frame_count, request.profile.duration, media_count, visualizer_count)
    except BaseException:
        output.discard()
        raise
    finally:
        media_pool.close()
        terminate_process_tree(decoder, logger, grace_seconds=1.5)
        terminate_process_tree(encoder, logger, grace_seconds=1.5)
        for stream in (getattr(decoder, "stdout", None), getattr(encoder, "stdin", None)):
            try:
                if stream is not None and not stream.closed:
                    stream.close()
            except OSError:
                pass
        shutil.rmtree(temporary_dir, ignore_errors=True)
