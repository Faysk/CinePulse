"""Preview-only restoration export runtime.

Exports are written to a sibling temporary file and atomically promoted only
when processing exits successfully. Cancellation and failures remove the
temporary artifact, so an interrupted experiment never masquerades as a
finished render.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

from .restoration_execute import build_preview_ffmpeg_command
from .restoration_preview import PreviewRestorationPlan
from .restoration_temporal_export import TemporalPreviewCancelled, stream_temporal_preview


class PreviewExportCancelled(RuntimeError):
    """Raised when a Preview export is explicitly cancelled."""


@dataclass(frozen=True)
class PreviewExportResult:
    output: Path
    command: tuple[str, ...]
    elapsed_seconds: float
    temporal_frames: int = 0
    temporal_regions_applied: int = 0
    temporal_regions_fallback: int = 0

    @property
    def used_temporal_reconstruction(self) -> bool:
        return self.temporal_frames > 0


def temporary_preview_output(output: Path) -> Path:
    """Return a unique sibling path that keeps the final container suffix."""

    suffix = output.suffix or ".mp4"
    stem = output.stem or "cinepulse-preview"
    return output.with_name(f".{stem}.cinepulse-preview-{uuid4().hex[:10]}{suffix}")


def ensure_preview_scratch_capacity(
    source: Path,
    scratch_dir: Path,
    *,
    minimum_free_bytes: int = 512 * 1024 * 1024,
    source_multiplier: float = 2.0,
) -> int:
    """Fail closed when the output volume is obviously too full.

    This is intentionally a coarse floor rather than an encoded-size promise.
    Heavy 8K/12K planning remains governed by ``restoration_delivery``.
    """

    if minimum_free_bytes < 0:
        raise ValueError("minimum_free_bytes cannot be negative")
    if source_multiplier < 0:
        raise ValueError("source_multiplier cannot be negative")
    scratch_dir.mkdir(parents=True, exist_ok=True)
    source_size = source.stat().st_size if source.exists() else 0
    required = max(int(minimum_free_bytes), int(source_size * source_multiplier))
    free = shutil.disk_usage(scratch_dir).free
    if free < required:
        raise OSError(
            f"Espaço insuficiente para o Preview: {free / (1024**3):.1f} GiB livres; "
            f"reserve pelo menos {required / (1024**3):.1f} GiB."
        )
    return required


def _terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def export_preview_restoration(
    ffmpeg: str,
    source: Path,
    output: Path,
    plan: PreviewRestorationPlan,
    *,
    ffprobe: str | None = None,
    cancel_event: threading.Event | None = None,
    video_codec: str = "libx264",
    crf: int = 16,
    preset: str = "slow",
    poll_interval: float = 0.1,
) -> PreviewExportResult:
    """Execute one isolated Preview export with cancellation and atomic finish.

    Overlay removal is never silently advertised as temporal while using the
    spatial ``delogo`` fallback. When selected regions exist this function
    requires FFprobe and routes the complete video through the bounded rolling
    temporal backend. Color-only work keeps the simpler one-process FFmpeg path.
    """

    if not source.is_file():
        raise FileNotFoundError(source)
    if output.resolve() == source.resolve():
        raise ValueError("Preview output cannot overwrite the source file")
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")

    output.parent.mkdir(parents=True, exist_ok=True)
    ensure_preview_scratch_capacity(source, output.parent)
    temporary = temporary_preview_output(output)
    cancel = cancel_event or threading.Event()
    started = time.monotonic()

    if plan.has_overlay_work:
        if not ffprobe:
            raise ValueError("FFprobe é obrigatório para exportar reconstrução temporal de overlays.")
        try:
            report = stream_temporal_preview(
                ffmpeg,
                ffprobe,
                source,
                temporary,
                plan,
                cancel_event=cancel,
                video_codec=video_codec,
                crf=crf,
                preset=preset,
            )
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise RuntimeError("Reconstrução temporal terminou sem arquivo Preview válido.")
            os.replace(temporary, output)
            return PreviewExportResult(
                output=output,
                command=("temporal-preview-stream", str(source), str(output)),
                elapsed_seconds=max(0.0, time.monotonic() - started),
                temporal_frames=report.frames_written,
                temporal_regions_applied=report.applied_regions,
                temporal_regions_fallback=report.fallback_regions,
            )
        except TemporalPreviewCancelled as exc:
            raise PreviewExportCancelled(str(exc)) from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    command = build_preview_ffmpeg_command(
        ffmpeg,
        source,
        temporary,
        plan,
        video_codec=video_codec,
        crf=crf,
        preset=preset,
    )
    process: subprocess.Popen | None = None
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    try:
        # FFmpeg can write enough diagnostics to fill an OS pipe during a long
        # render. A temporary file keeps cancellation polling non-blocking while
        # still preserving a useful error tail for the UI.
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stderr_log:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=stderr_log,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            while process.poll() is None:
                if cancel.is_set():
                    _terminate_process(process)
                    raise PreviewExportCancelled("Exportação Preview cancelada.")
                time.sleep(poll_interval)

            stderr_log.flush()
            stderr_log.seek(0)
            stderr_text = stderr_log.read()

        if process.returncode != 0:
            tail = (stderr_text or "").strip()[-1600:]
            raise RuntimeError(f"FFmpeg falhou na exportação Preview.\n{tail}".strip())
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError("FFmpeg terminou sem produzir um arquivo Preview válido.")
        os.replace(temporary, output)
        return PreviewExportResult(
            output=output,
            command=tuple(command),
            elapsed_seconds=max(0.0, time.monotonic() - started),
        )
    finally:
        if process is not None and cancel.is_set() and process.poll() is None:
            _terminate_process(process)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
