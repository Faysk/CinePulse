"""Streaming temporal reconstruction backend for Preview restoration exports.

This module is intentionally isolated from Stable. It decodes RGB frames through
FFmpeg, reconstructs selected overlay regions from nearby source frames with a
bounded rolling window, and feeds the reconstructed stream into a second FFmpeg
process. Audio is mapped from the original source and color restoration is
applied only after temporal reconstruction.

The rawvideo bridge does not carry source timestamps. For that reason this path
fails closed for sources whose average and nominal frame rates disagree (a
strong VFR signal) instead of silently retiming them to CFR. It also enforces a
bounded temporal working-set estimate before decoding, which is especially
important for experimental 8K/12K jobs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from typing import BinaryIO

import numpy as np

from .restoration_inpaint import TemporalReconstructionPolicy, reconstruct_region_temporally
from .restoration_preview import PreviewRestorationPlan
from .process_control import popen_group_kwargs, terminate_process_tree


class TemporalPreviewCancelled(RuntimeError):
    """Raised when a streaming temporal Preview export is cancelled."""


DEFAULT_MAX_TEMPORAL_WORKING_SET_BYTES = 2 * 1024**3


@dataclass(frozen=True)
class PreviewVideoGeometry:
    width: int
    height: int
    fps: float
    nominal_fps: float | None = None

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.fps <= 0:
            raise ValueError("invalid Preview video geometry")
        if self.nominal_fps is not None and self.nominal_fps <= 0:
            raise ValueError("invalid nominal Preview frame rate")

    @property
    def frame_bytes(self) -> int:
        return self.width * self.height * 3

    @property
    def suspected_vfr(self) -> bool:
        """Return True when ffprobe exposes materially different avg/base rates.

        This is deliberately conservative. Raw RGB frames do not preserve PTS,
        so the temporal exporter must not pretend it can safely maintain VFR
        timing when ffprobe already signals a mismatch.
        """

        if self.nominal_fps is None:
            return False
        scale = max(self.fps, self.nominal_fps, 1.0)
        return abs(self.fps - self.nominal_fps) / scale > 0.001

    def estimated_temporal_working_set(self, policy: TemporalReconstructionPolicy) -> int:
        """Estimate bounded resident RGB storage for the rolling window.

        The rolling deque can retain at most ``2 * radius + 1`` decoded frames.
        Reconstruction also creates a target copy, so reserve one additional
        full-frame slot. Region-local arrays are deliberately not counted as
        full frames and remain bounded by the selected overlay sizes.
        """

        resident_frames = (2 * int(policy.radius) + 1) + 3
        return self.frame_bytes * resident_frames


def _parse_rate(value: str) -> float:
    text = str(value or "").strip()
    if not text or text == "0/0":
        raise ValueError("invalid frame rate")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            raise ValueError("invalid frame rate")
        result = float(numerator) / denominator_value
    else:
        result = float(text)
    if result <= 0:
        raise ValueError("invalid frame rate")
    return result


def _optional_rate(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text == "0/0":
        return None
    try:
        return _parse_rate(text)
    except (TypeError, ValueError):
        return None


def probe_preview_geometry(ffprobe: str, source: Path) -> PreviewVideoGeometry:
    """Read only the geometry/timing hints needed by the rawvideo path."""

    if not ffprobe:
        raise ValueError("ffprobe executable is required for temporal Preview export")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "FFprobe falhou no Preview temporal.")
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams") or []
    if not streams:
        raise RuntimeError("A fonte não possui stream de vídeo para reconstrução temporal.")
    stream = streams[0]
    avg_fps = _optional_rate(stream.get("avg_frame_rate"))
    nominal_fps = _optional_rate(stream.get("r_frame_rate"))
    fps = avg_fps or nominal_fps
    if fps is None:
        raise RuntimeError("Não foi possível determinar o frame rate do vídeo Preview.")
    return PreviewVideoGeometry(
        width=int(stream.get("width") or 0),
        height=int(stream.get("height") or 0),
        fps=fps,
        nominal_fps=nominal_fps,
    )


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def reconstruct_window_target(
    frames: list[np.ndarray],
    *,
    target_index: int,
    plan: PreviewRestorationPlan,
    policy: TemporalReconstructionPolicy,
) -> tuple[np.ndarray, int, int]:
    """Reconstruct one target while keeping donor frames immutable.

    Regions that cannot gather enough context-compatible donors remain unchanged;
    callers receive explicit applied/fallback counts instead of silently
    pretending temporal reconstruction succeeded.
    """

    if not 0 <= target_index < len(frames):
        raise IndexError("target_index outside rolling window")
    output = np.asarray(frames[target_index]).copy()
    applied = 0
    fallback = 0
    for region in plan.regions:
        result = reconstruct_region_temporally(
            frames,
            target_index=target_index,
            region=region,
            policy=policy,
        )
        if result.applied:
            candidate = result.frame
            x, y, width, height = region.to_pixels(output.shape[1], output.shape[0])
            output[y : y + height, x : x + width] = candidate[y : y + height, x : x + width]
            applied += 1
        else:
            fallback += 1
    return output, applied, fallback


@dataclass(frozen=True)
class TemporalStreamReport:
    frames_written: int
    applied_regions: int
    fallback_regions: int


def stream_temporal_preview(
    ffmpeg: str,
    ffprobe: str,
    source: Path,
    output: Path,
    plan: PreviewRestorationPlan,
    *,
    cancel_event: threading.Event | None = None,
    video_codec: str = "libx264",
    crf: int = 16,
    preset: str = "slow",
    policy: TemporalReconstructionPolicy = TemporalReconstructionPolicy(),
    max_working_set_bytes: int = DEFAULT_MAX_TEMPORAL_WORKING_SET_BYTES,
) -> TemporalStreamReport:
    """Run bounded rolling-window temporal reconstruction into a complete file."""

    if not plan.has_overlay_work:
        raise ValueError("temporal Preview export requires selected overlay regions")
    if not 0 <= int(crf) <= 51:
        raise ValueError("crf must be between 0 and 51")
    if int(max_working_set_bytes) <= 0:
        raise ValueError("max_working_set_bytes must be positive")

    geometry = probe_preview_geometry(ffprobe, source)
    if geometry.suspected_vfr:
        raise RuntimeError(
            "A reconstrução temporal Preview não preserva timestamps VFR com segurança; "
            "esta fonte foi recusada para evitar dessincronização ou retiming silencioso."
        )
    estimated_working_set = geometry.estimated_temporal_working_set(policy)
    if estimated_working_set > int(max_working_set_bytes):
        gib = estimated_working_set / 1024**3
        limit_gib = int(max_working_set_bytes) / 1024**3
        raise RuntimeError(
            f"Reconstrução temporal exigiria aproximadamente {gib:.2f} GiB de RGB em memória "
            f"(limite Preview: {limit_gib:.2f} GiB). Reduza resolução/janela ou use um caminho sem reconstrução temporal."
        )

    cancel = cancel_event or threading.Event()
    decoder: subprocess.Popen | None = None
    encoder: subprocess.Popen | None = None
    cancel_watcher_stop = threading.Event()
    cancel_watcher: threading.Thread | None = None
    frames_written = 0
    applied_regions = 0
    fallback_regions = 0

    decoder_command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    encoder_command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s:v",
        f"{geometry.width}x{geometry.height}",
        "-r",
        f"{geometry.fps:.8f}",
        "-i",
        "pipe:0",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
    ]
    if plan.color_filter:
        encoder_command.extend(["-vf", plan.color_filter])
    encoder_command.extend(
        [
            "-c:v",
            video_codec,
            "-preset",
            preset,
            "-crf",
            str(int(crf)),
            "-c:a",
            "copy",
            "-shortest",
            str(output),
        ]
    )

    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as decoder_log, tempfile.TemporaryFile(
        mode="w+", encoding="utf-8", errors="replace"
    ) as encoder_log:
        try:
            if cancel.is_set():
                raise TemporalPreviewCancelled("Exportação temporal Preview cancelada.")
            decoder = subprocess.Popen(
                decoder_command,
                stdout=subprocess.PIPE,
                stderr=decoder_log,
                **popen_group_kwargs(),
            )
            encoder = subprocess.Popen(
                encoder_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=encoder_log,
                **popen_group_kwargs(),
            )
            if decoder.stdout is None or encoder.stdin is None:
                raise RuntimeError("Não foi possível abrir os pipes do Preview temporal.")

            def watch_cancellation() -> None:
                # Rawvideo read/write calls are intentionally blocking to keep
                # memory bounded. This watcher is the escape hatch: cancelling
                # the Preview tears down both process groups, which closes the
                # pipes and unblocks the streaming worker immediately.
                while not cancel_watcher_stop.wait(0.05):
                    if not cancel.is_set():
                        continue
                    for process in (decoder, encoder):
                        if process is not None:
                            terminate_process_tree(process, grace_seconds=1.0)
                    return

            cancel_watcher = threading.Thread(
                target=watch_cancellation,
                name="cinepulse-preview-temporal-cancel",
                daemon=True,
            )
            cancel_watcher.start()

            window: deque[tuple[int, np.ndarray]] = deque()
            next_target = 0
            decoded_index = -1
            eof = False

            while not eof:
                if cancel.is_set():
                    raise TemporalPreviewCancelled("Exportação temporal Preview cancelada.")
                raw = _read_exact(decoder.stdout, geometry.frame_bytes)
                if not raw:
                    eof = True
                elif len(raw) != geometry.frame_bytes:
                    raise RuntimeError("FFmpeg encerrou rawvideo no meio de um frame temporal.")
                else:
                    decoded_index += 1
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape(geometry.height, geometry.width, 3).copy()
                    window.append((decoded_index, frame))

                while window and (eof or decoded_index >= next_target + policy.radius):
                    first_index = window[0][0]
                    last_index = window[-1][0]
                    if next_target < first_index:
                        next_target = first_index
                    if next_target > last_index:
                        break
                    local_target = next_target - first_index
                    frames = [item[1] for item in window]
                    restored, applied, fallback = reconstruct_window_target(
                        frames,
                        target_index=local_target,
                        plan=plan,
                        policy=policy,
                    )
                    encoder.stdin.write(restored.tobytes(order="C"))
                    frames_written += 1
                    applied_regions += applied
                    fallback_regions += fallback
                    next_target += 1
                    while window and window[0][0] < next_target - policy.radius:
                        window.popleft()

                if eof:
                    break

            encoder.stdin.close()
            encoder.stdin = None
            decoder_return = decoder.wait()
            encoder_return = encoder.wait()
            if cancel.is_set():
                raise TemporalPreviewCancelled("Exportação temporal Preview cancelada.")
            if decoder_return != 0 or encoder_return != 0:
                decoder_log.seek(0)
                encoder_log.seek(0)
                tail = (decoder_log.read() + "\n" + encoder_log.read()).strip()[-2000:]
                raise RuntimeError(f"FFmpeg falhou no Preview temporal.\n{tail}".strip())
            if frames_written <= 0 or not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError("Preview temporal terminou sem produzir vídeo válido.")
            return TemporalStreamReport(
                frames_written=frames_written,
                applied_regions=applied_regions,
                fallback_regions=fallback_regions,
            )
        except (BrokenPipeError, OSError, ValueError) as exc:
            if cancel.is_set():
                raise TemporalPreviewCancelled("Exportação temporal Preview cancelada.") from exc
            raise
        finally:
            cancel_watcher_stop.set()
            for process in (decoder, encoder):
                if process is not None and process.poll() is None:
                    terminate_process_tree(process, grace_seconds=1.0)
            if cancel_watcher is not None and cancel_watcher is not threading.current_thread():
                cancel_watcher.join(timeout=2.0)
