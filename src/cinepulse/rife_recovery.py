"""Crash-safe recovery for an interrupted chunked RIFE render.

This module intentionally targets the Phase 6 chunk layout produced by
``Studio._interpolate_rife``.  It never prunes scratch data and only promotes a
segment after FFmpeg and FFprobe have both accepted it.  A repeated invocation
therefore resumes from the last committed segment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .color_pipeline import ColorProfile, build_color_pipeline
from .delivery import PROFILE_AUTO, build_delivery_plan, detect_ffmpeg_encoders
from .matroska_quality import inspect_matroska_segment
from .process_control import popen_group_kwargs, terminate_process_tree
from .verification import VerifyExpectation, quick_verify


class RecoveryError(RuntimeError):
    """Raised when recovery cannot continue without risking existing work."""


@dataclass(frozen=True)
class ChunkPlan:
    index: int
    source_start: int
    source_frames: int
    target_frames: int


@dataclass(frozen=True)
class RecoveryContract:
    job_id: str
    source: Path
    cache: Path
    output: Path
    history_dir: Path
    job_dir: Path
    chunk_root: Path
    app_root: Path
    ffmpeg: Path
    ffprobe: Path
    rife_exe: Path
    rife_model: Path
    realesrgan_model: Path
    duration: float
    source_width: int
    source_height: int
    source_fps: float
    target_width: int
    target_height: int
    target_fps: float
    total_source_frames: int
    total_target_frames: int
    chunk_frames: int
    cpu_threads: int

    @property
    def state_path(self) -> Path:
        return self.job_dir / "recovery-state.json"

    @property
    def log_path(self) -> Path:
        return self.history_dir / "recovery.log"

    @property
    def master_path(self) -> Path:
        return self.job_dir / "recovered_rife_master.mkv"

    @property
    def result_path(self) -> Path:
        return self.history_dir / "recovery-result.json"


class RecoveryLogger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = path.open("a", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            self._handle.close()

    def __call__(self, message: str) -> None:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        line = f"[{stamp}] {message}"
        with self._lock:
            self._handle.write(line + "\n")
            self._handle.flush()
        print(line, flush=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecoveryError(f"Nao foi possivel ler {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RecoveryError(f"JSON invalido em {path}")
    return payload


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve(strict=False))) == os.path.normcase(str(right.resolve(strict=False)))


def _require_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RecoveryError(f"{label} ausente ou vazio: {path}")
    return path


def _require_dir(path: Path, label: str) -> Path:
    if not path.is_dir():
        raise RecoveryError(f"{label} ausente: {path}")
    return path


def _run_json(command: list[str], label: str) -> dict[str, Any]:
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RecoveryError(f"{label} falhou: {(result.stderr or result.stdout).strip()[-2000:]}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RecoveryError(f"{label} retornou JSON invalido: {exc}") from exc
    if not isinstance(payload, dict):
        raise RecoveryError(f"{label} retornou uma estrutura inesperada")
    return payload


def _probe(ffprobe: Path, path: Path) -> dict[str, Any]:
    return _run_json(
        [str(ffprobe), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        f"FFprobe de {path.name}",
    )


def _video_stream(info: dict[str, Any]) -> dict[str, Any]:
    return next((item for item in info.get("streams", []) if item.get("codec_type") == "video"), {})


def _ratio(value: Any) -> float:
    text = str(value or "0/0")
    if "/" in text:
        left, right = text.split("/", 1)
        return float(left) / float(right) if float(right) else 0.0
    return float(text or 0.0)


def _duration(info: dict[str, Any]) -> float:
    value = info.get("format", {}).get("duration")
    if value in (None, "N/A"):
        value = _video_stream(info).get("duration")
    return float(value or 0.0)


def ai_cache_key(
    source: Path,
    model: Path,
    *,
    start_time: float,
    duration: float,
    source_fps: float,
    source_width: int,
    source_height: int,
) -> str:
    source_stat = source.stat()
    model_stat = model.stat() if model.is_file() else None
    identity = {
        "path": str(source.resolve()),
        "size": source_stat.st_size,
        "mtime": source_stat.st_mtime_ns,
        "start": round(start_time, 5),
        "duration": round(duration, 5),
        "fps": round(source_fps, 5),
        "width": source_width,
        "height": source_height,
        "model_size": model_stat.st_size if model_stat else 0,
        "model_mtime": model_stat.st_mtime_ns if model_stat else 0,
        "scale": 2,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def source_chunk_counts(total_source_frames: int, chunk_frames: int) -> list[int]:
    if total_source_frames < 2 or chunk_frames < 2:
        raise ValueError("RIFE recovery requires at least two frames per chunk")
    counts: list[int] = []
    processed = 0
    while processed < total_source_frames:
        remaining = total_source_frames - processed
        count = min(chunk_frames, remaining)
        if remaining - count == 1:
            count += 1
        count = min(count, remaining)
        if count < 2:
            break
        counts.append(count)
        processed += count
    if processed != total_source_frames:
        raise ValueError(f"Unable to cover all source frames: {processed}/{total_source_frames}")
    return counts


def original_target_counts(source_counts: Iterable[int], source_fps: float, target_fps: float) -> list[int]:
    return [max(2, round(count / source_fps * target_fps)) for count in source_counts]


def frame_count_from_container_duration(duration: float, fps: float) -> int:
    """Infer a short segment's frame count from its Matroska duration.

    Matroska timestamps use a millisecond time base in these FFV1 segments, so
    their reported durations are rounded by up to roughly one millisecond.
    Rounding duration * FPS recovers the committed count without decoding each
    8K segment, which would make every crash recovery take hours.
    """

    if duration <= 0 or fps <= 0:
        raise ValueError("duration and fps must be positive")
    return max(1, round(duration * fps))


def remaining_schedule(
    *,
    source_counts: list[int],
    completed_chunks: int,
    completed_target_frames: int,
    total_target_frames: int,
) -> list[ChunkPlan]:
    """Distribute remaining target frames exactly across the remaining chunks.

    The rc.6 implementation rounds every eight-frame chunk independently and
    loses roughly 43 frames over this 8K/120 render.  Existing segments cannot
    be changed, so recovery distributes the residual over future chunks using a
    cumulative ratio.  This preserves smooth cadence and reaches the exact
    final frame contract without a large correction in the last chunk.
    """

    if completed_chunks < 0 or completed_chunks > len(source_counts):
        raise ValueError("completed_chunks is outside the source schedule")
    remaining_counts = source_counts[completed_chunks:]
    remaining_source = sum(remaining_counts)
    remaining_target = total_target_frames - completed_target_frames
    if remaining_counts and (remaining_source <= 0 or remaining_target < 2 * len(remaining_counts)):
        raise ValueError("remaining target frame budget is invalid")
    source_start = sum(source_counts[:completed_chunks])
    cumulative_source = 0
    cumulative_target = 0
    plans: list[ChunkPlan] = []
    for offset, count in enumerate(remaining_counts, start=completed_chunks + 1):
        cumulative_source += count
        target_after = round(cumulative_source / remaining_source * remaining_target)
        desired = target_after - cumulative_target
        if desired < 2:
            raise ValueError(f"chunk {offset} would receive fewer than two target frames")
        plans.append(ChunkPlan(offset, source_start, count, desired))
        source_start += count
        cumulative_target = target_after
    if cumulative_target != remaining_target:
        raise ValueError(f"remaining schedule mismatch: {cumulative_target}/{remaining_target}")
    return plans


def _segment_index(path: Path) -> int:
    try:
        return int(path.stem.split("_")[-1])
    except (ValueError, IndexError) as exc:
        raise RecoveryError(f"Nome de segmento inesperado: {path.name}") from exc


def contiguous_segments(chunk_root: Path) -> list[Path]:
    # Five wildcard characters deliberately exclude .partial/.repair files.
    segments = sorted(chunk_root.glob("segment_?????.mkv"), key=_segment_index)
    for expected, path in enumerate(segments, start=1):
        if _segment_index(path) != expected:
            raise RecoveryError(f"Sequencia de segmentos interrompida: esperado {expected}, encontrado {path.name}")
    return segments


def _validate_video(
    *,
    ffprobe: Path,
    path: Path,
    width: int,
    height: int,
    fps: float,
    codec: str | None = None,
    duration_minimum: float = 0.01,
) -> dict[str, Any]:
    info = _probe(ffprobe, path)
    video = _video_stream(info)
    actual_size = (int(video.get("width") or 0), int(video.get("height") or 0))
    actual_fps = _ratio(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    actual_codec = str(video.get("codec_name") or "")
    actual_duration = _duration(info)
    if actual_size != (width, height):
        raise RecoveryError(f"{path.name}: resolucao {actual_size}, esperada {(width, height)}")
    if abs(actual_fps - fps) > 0.02:
        raise RecoveryError(f"{path.name}: FPS {actual_fps:.5f}, esperado {fps:.5f}")
    if codec and actual_codec != codec:
        raise RecoveryError(f"{path.name}: codec {actual_codec}, esperado {codec}")
    if actual_duration < duration_minimum:
        raise RecoveryError(f"{path.name}: duracao invalida {actual_duration:.6f}s")
    return info


def load_contract(args: argparse.Namespace) -> RecoveryContract:
    app_root = Path(args.app_root).resolve()
    history_dir = Path(args.history_dir).resolve()
    chunk_root = Path(args.chunk_root).resolve()
    cache = Path(args.cache).resolve()
    job = _load_json(history_dir / "job.json")
    plan = _load_json(history_dir / "plan.json")
    contracts = _load_json(history_dir / "contracts.json")
    settings = job.get("settings", {})
    expected = contracts.get("verification_expected", {})
    source_spec = plan.get("source", {})
    target_spec = plan.get("target", {})
    storage = contracts.get("storage", {})

    source = Path(args.source or settings.get("video", "")).resolve()
    output = Path(args.output or settings.get("output", "")).resolve()
    expected_source = Path(settings.get("video", "")).resolve()
    if not _same_path(source, expected_source):
        raise RecoveryError(f"Fonte informada nao corresponde ao job: {source} != {expected_source}")
    if _same_path(source, output):
        raise RecoveryError("Saida nao pode sobrescrever a fonte")
    if job.get("job_id") != history_dir.name:
        raise RecoveryError("Diretorio de historico nao corresponde ao job_id")
    if settings.get("mode") != "Melhorar vídeo original — manter duração e conteúdo":
        raise RecoveryError("Este recuperador exige o modo de video original")
    if settings.get("interpolation") != "RIFE IA — movimento natural":
        raise RecoveryError("O job nao usa RIFE")
    if settings.get("effects"):
        raise RecoveryError("Este job inesperadamente contem VFX ativos")
    if not bool(settings.get("preserve_audio")):
        raise RecoveryError("Este job deveria preservar o audio original")

    ffmpeg = app_root / "components" / "ffmpeg" / "bin" / "ffmpeg.exe"
    ffprobe = app_root / "components" / "ffmpeg" / "bin" / "ffprobe.exe"
    rife_dir = app_root / "components" / "ai" / "models" / "rife" / "portable" / "rife-ncnn-vulkan-20221029-windows"
    rife_exe = rife_dir / "rife-ncnn-vulkan.exe"
    rife_model = rife_dir / "rife-v4.6"
    realesrgan_model = app_root / "components" / "real-esrgan" / "models" / "realesr-animevideov3-x2.bin"
    for path, label in (
        (source, "Video original"), (cache, "Master Real-ESRGAN"),
        (ffmpeg, "FFmpeg"), (ffprobe, "FFprobe"), (rife_exe, "RIFE"),
        (rife_model / "flownet.bin", "Modelo RIFE bin"),
        (rife_model / "flownet.param", "Modelo RIFE param"),
        (realesrgan_model, "Modelo Real-ESRGAN"),
    ):
        _require_file(path, label)
    _require_dir(chunk_root, "Diretorio de segmentos")
    job_dir = chunk_root.parent
    if not chunk_root.name.startswith("rife_") or not job_dir.name.startswith("job_"):
        raise RecoveryError("Layout scratch inesperado; recusando operar fora de job_/rife_*")

    duration = float(expected.get("duration") or 0.0)
    source_fps = float(source_spec.get("fps") or 0.0)
    target_fps = float(target_spec.get("fps") or expected.get("fps") or 0.0)
    contract = RecoveryContract(
        job_id=str(job["job_id"]), source=source, cache=cache, output=output,
        history_dir=history_dir, job_dir=job_dir, chunk_root=chunk_root, app_root=app_root,
        ffmpeg=ffmpeg, ffprobe=ffprobe, rife_exe=rife_exe, rife_model=rife_model,
        realesrgan_model=realesrgan_model, duration=duration,
        source_width=int(source_spec["width"]), source_height=int(source_spec["height"]),
        source_fps=source_fps, target_width=int(target_spec["width"]),
        target_height=int(target_spec["height"]), target_fps=target_fps,
        total_source_frames=round(duration * source_fps), total_target_frames=round(duration * target_fps),
        chunk_frames=int(storage.get("rife_chunk_frames") or 0),
        cpu_threads=int(settings.get("cpu_threads") or 1),
    )
    if min(contract.duration, contract.source_fps, contract.target_fps) <= 0:
        raise RecoveryError("Contrato temporal invalido")
    return contract


def _source_identity(contract: RecoveryContract) -> dict[str, Any]:
    source_stat = contract.source.stat()
    cache_stat = contract.cache.stat()
    return {
        "source": str(contract.source), "source_size": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns, "cache": str(contract.cache),
        "cache_size": cache_stat.st_size, "cache_mtime_ns": cache_stat.st_mtime_ns,
    }


def validate_contract(contract: RecoveryContract, log: Callable[[str], None], *, full_scan: bool = True) -> tuple[list[Path], int]:
    source_info = _probe(contract.ffprobe, contract.source)
    source_video = _video_stream(source_info)
    if (int(source_video.get("width") or 0), int(source_video.get("height") or 0)) != (contract.source_width, contract.source_height):
        raise RecoveryError("Resolucao da fonte mudou desde o inicio do job")
    if abs(_ratio(source_video.get("avg_frame_rate")) - contract.source_fps) > 0.001:
        raise RecoveryError("FPS da fonte mudou desde o inicio do job")
    if abs(_duration(source_info) - contract.duration) > 0.01:
        raise RecoveryError("Duracao da fonte mudou desde o inicio do job")

    expected_cache_key = ai_cache_key(
        contract.source, contract.realesrgan_model, start_time=0.0, duration=contract.duration,
        source_fps=contract.source_fps, source_width=contract.source_width, source_height=contract.source_height,
    )
    if contract.cache.stem != expected_cache_key:
        raise RecoveryError(f"Cache nao pertence a esta fonte/modelo: {contract.cache.stem} != {expected_cache_key}")
    cache_info = _validate_video(
        ffprobe=contract.ffprobe, path=contract.cache, width=contract.target_width,
        height=contract.target_height, fps=contract.source_fps, codec="ffv1",
        duration_minimum=contract.duration - 1.0,
    )
    log(f"CACHE_OK key={expected_cache_key} duration={_duration(cache_info):.3f}s size={contract.cache.stat().st_size}")

    segments = contiguous_segments(contract.chunk_root)
    source_counts = source_chunk_counts(contract.total_source_frames, contract.chunk_frames)
    original_targets = original_target_counts(source_counts, contract.source_fps, contract.target_fps)
    if len(segments) > len(source_counts):
        raise RecoveryError("Ha mais segmentos que lotes previstos")
    completed_target = sum(original_targets[:len(segments)])
    if full_scan:
        completed_target = 0
        for number, segment in enumerate(segments, start=1):
            info = _validate_video(
                ffprobe=contract.ffprobe, path=segment, width=contract.target_width,
                height=contract.target_height, fps=contract.target_fps, codec="ffv1",
            )
            actual_duration = _duration(info)
            inferred_frames = frame_count_from_container_duration(actual_duration, contract.target_fps)
            nominal_frames = original_targets[number - 1]
            # Recovery deliberately adds one frame to selected chunks so that
            # independent per-chunk rounding does not leave the final render
            # short.  Validate that permitted residual distribution instead of
            # comparing every resumed segment with the old nominal schedule.
            if inferred_frames not in {nominal_frames, nominal_frames + 1}:
                raise RecoveryError(
                    f"{segment.name}: duracao {actual_duration:.6f}s implica {inferred_frames} quadros; "
                    f"esperado {nominal_frames} ou {nominal_frames + 1}"
                )
            inferred_duration = inferred_frames / contract.target_fps
            if abs(actual_duration - inferred_duration) > 0.002:
                raise RecoveryError(
                    f"{segment.name}: timestamp {actual_duration:.6f}s inconsistente com "
                    f"{inferred_frames} quadros a {contract.target_fps:.5f} fps"
                )
            completed_target += inferred_frames
            if number % 100 == 0 or number == len(segments):
                log(f"SEGMENT_SCAN {number}/{len(segments)}")
        if contract.state_path.is_file():
            prior_state = _load_json(contract.state_path)
            prior_segments = int(prior_state.get("completed_segments") or 0)
            prior_target = int(prior_state.get("completed_target_frames") or 0)
            if prior_segments == len(segments) and prior_target and prior_target != completed_target:
                raise RecoveryError(
                    f"Checkpoint registra {prior_target} quadros em {prior_segments} segmentos, "
                    f"mas a verificacao encontrou {completed_target}"
                )
    log(
        f"SEGMENTS_OK count={len(segments)} source_frames={sum(source_counts[:len(segments)])}/"
        f"{contract.total_source_frames} target_frames={completed_target}/{contract.total_target_frames}"
    )
    return segments, completed_target


def _gpu_snapshot() -> str:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return "GPU telemetry unavailable"
    result = subprocess.run(
        [executable, "--query-gpu=utilization.gpu,utilization.memory,memory.used,temperature.gpu,power.draw,pstate",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )
    return "GPU " + (result.stdout.strip() if result.returncode == 0 else "telemetry failed")


def _run_logged(
    command: list[str],
    *,
    label: str,
    log: Callable[[str], None],
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
    progress_probe: Callable[[], int] | None = None,
    stop_file: Path | None = None,
) -> None:
    log(f"START {label}: {subprocess.list2cmdline(command)}")
    process = subprocess.Popen(
        command, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1, **popen_group_kwargs(),
    )
    messages: queue.Queue[str] = queue.Queue()
    recent: list[str] = []

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            messages.put(line.rstrip())

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    started = time.monotonic()
    last_activity = started
    last_gpu = 0.0
    last_progress = progress_probe() if progress_probe else 0
    try:
        while process.poll() is None:
            drained = False
            while True:
                try:
                    message = messages.get_nowait()
                except queue.Empty:
                    break
                if message:
                    drained = True
                    recent.append(message)
                    del recent[:-80]
                    if message.startswith(("frame=", "progress=", "[")) or "error" in message.casefold():
                        log(f"{label}: {message}")
            if drained:
                last_activity = time.monotonic()
            if progress_probe:
                current = progress_probe()
                if current != last_progress:
                    last_progress = current
                    last_activity = time.monotonic()
            now = time.monotonic()
            if now - last_gpu >= 15:
                log(f"{label}: {_gpu_snapshot()} progress_files={last_progress}")
                last_gpu = now
            if stop_file and stop_file.exists():
                raise KeyboardInterrupt(f"Stop file detected: {stop_file}")
            if timeout_seconds and now - last_activity > timeout_seconds:
                raise RecoveryError(f"{label} sem progresso por {timeout_seconds / 60:.1f} minutos")
            time.sleep(0.5)
    except BaseException:
        terminate_process_tree(process, log)
        raise
    code = process.wait()
    thread.join(timeout=3)
    while True:
        try:
            message = messages.get_nowait()
        except queue.Empty:
            break
        if message:
            recent.append(message)
            del recent[:-80]
    if code:
        raise RecoveryError(f"{label} terminou com codigo {code}: {' | '.join(recent[-12:])}")
    log(f"DONE {label} elapsed={time.monotonic() - started:.1f}s")


def _quarantine_incomplete(contract: RecoveryContract, next_index: int, log: Callable[[str], None]) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidates = [
        contract.chunk_root / f"chunk_{next_index:05d}_in",
        contract.chunk_root / f"chunk_{next_index:05d}_out",
        contract.chunk_root / f"chunk_{next_index:05d}_out_resampled",
        contract.chunk_root / f"segment_{next_index:05d}.partial.mkv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        target = contract.job_dir / f"interrupted_{path.name}_{stamp}"
        os.replace(path, target)
        log(f"QUARANTINE {path} -> {target}")


def _write_state(
    contract: RecoveryContract,
    *,
    phase: str,
    completed_segments: int,
    completed_source_frames: int,
    completed_target_frames: int,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema": 1, "job_id": contract.job_id, "phase": phase,
        "updated_at": time.time(), "completed_segments": completed_segments,
        "completed_source_frames": completed_source_frames,
        "completed_target_frames": completed_target_frames,
        "total_source_frames": contract.total_source_frames,
        "total_target_frames": contract.total_target_frames,
        **_source_identity(contract),
    }
    if extra:
        payload.update(extra)
    _atomic_json(contract.state_path, payload)


def _safe_rmtree_child(root: Path, path: Path) -> None:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved.parent != resolved_root:
        raise RecoveryError(f"Recusando remover diretorio fora do lote: {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)


def _validate_png_sequence(frames: list[Path], expected: int, *, label: str) -> None:
    png_signature = b"\x89PNG\r\n\x1a\n"
    png_iend = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    if len(frames) != expected:
        raise RecoveryError(f"{label}: produziu {len(frames)}/{expected} arquivos PNG")
    for frame in frames:
        try:
            with frame.open("rb") as handle:
                if handle.read(8) != png_signature:
                    raise RecoveryError(f"{label}: assinatura PNG invalida em {frame.name}")
                handle.seek(-12, os.SEEK_END)
                if handle.read(12) != png_iend:
                    raise RecoveryError(f"{label}: PNG truncado em {frame.name}")
        except OSError as exc:
            raise RecoveryError(f"{label}: nao foi possivel validar {frame.name}: {exc}") from exc


def generate_rife_frames_safe(
    contract: RecoveryContract,
    incoming: Path,
    outgoing: Path,
    *,
    source_frames: int,
    target_frames: int,
    label: str,
    log: Callable[[str], None],
    timeout_minutes: float,
    stop_file: Path,
) -> tuple[list[Path], Path]:
    """Generate native 2x UHD frames, then uniformly retime odd counts."""

    native_target = source_frames * 2
    rife = [
        str(contract.rife_exe), "-i", str(incoming), "-o", str(outgoing),
        "-n", str(native_target), "-m", str(contract.rife_model),
        "-g", "0", "-j", "1:1:1", "-u", "-f", "%08d.png",
    ]
    _run_logged(
        rife,
        label=label,
        log=log,
        cwd=contract.rife_exe.parent,
        timeout_seconds=timeout_minutes * 60,
        progress_probe=lambda: len(list(outgoing.glob("*.png"))),
        stop_file=stop_file,
    )
    native_frames = sorted(outgoing.glob("*.png"))
    _validate_png_sequence(native_frames, native_target, label=label)
    if target_frames == native_target:
        return native_frames, outgoing

    resampled = outgoing.with_name(outgoing.name + "_resampled")
    resampled.mkdir(parents=False, exist_ok=False)
    first_number = int(native_frames[0].stem)
    input_rate = max(1, native_target - 1)
    output_rate = max(1, target_frames - 1)
    retime = [
        str(contract.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-framerate", str(input_rate), "-start_number", str(first_number),
        "-i", str(outgoing / "%08d.png"),
        "-vf", f"framerate=fps={output_rate}:interp_start=0:interp_end=255:scene=100",
        "-frames:v", str(target_frames), "-start_number", "1",
        "-progress", "pipe:1", "-nostats", str(resampled / "%08d.png"),
    ]
    _run_logged(
        retime,
        label=label + "-retime",
        log=log,
        timeout_seconds=timeout_minutes * 60,
        progress_probe=lambda: len(list(resampled.glob("*.png"))),
        stop_file=stop_file,
    )
    retimed_frames = sorted(resampled.glob("*.png"))
    _validate_png_sequence(retimed_frames, target_frames, label=label + "-retime")
    log(f"RIFE_RETIME native={native_target} target={target_frames} mode=uniform-blend")
    return retimed_frames, resampled


def resume_rife(contract: RecoveryContract, log: Callable[[str], None], *, timeout_minutes: float) -> Path:
    segments, completed_target = validate_contract(contract, log, full_scan=True)
    source_counts = source_chunk_counts(contract.total_source_frames, contract.chunk_frames)
    completed_source = sum(source_counts[:len(segments)])
    schedule = remaining_schedule(
        source_counts=source_counts, completed_chunks=len(segments),
        completed_target_frames=completed_target, total_target_frames=contract.total_target_frames,
    )
    _write_state(
        contract, phase="rife", completed_segments=len(segments),
        completed_source_frames=completed_source, completed_target_frames=completed_target,
        extra={"remaining_chunks": len(schedule)},
    )
    if schedule:
        _quarantine_incomplete(contract, schedule[0].index, log)
    stop_file = contract.job_dir / "STOP_RECOVERY"
    for position, chunk in enumerate(schedule, start=1):
        incoming = contract.chunk_root / f"chunk_{chunk.index:05d}_in"
        outgoing = contract.chunk_root / f"chunk_{chunk.index:05d}_out"
        incoming.mkdir(parents=False, exist_ok=False)
        outgoing.mkdir(parents=False, exist_ok=False)
        chunk_start = chunk.source_start / contract.source_fps
        chunk_duration = chunk.source_frames / contract.source_fps
        log(
            f"CHUNK {chunk.index}/{len(source_counts)} remaining={len(schedule) - position + 1} "
            f"source={chunk.source_start + 1}-{chunk.source_start + chunk.source_frames} "
            f"target={chunk.target_frames}"
        )
        extract = [
            str(contract.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-ss", f"{chunk_start:.6f}", "-i", str(contract.cache), "-map", "0:v:0", "-an",
            "-vf", f"fps={contract.source_fps:.8f}", "-frames:v", str(chunk.source_frames),
            "-start_number", "0", "-progress", "pipe:1", "-nostats", str(incoming / "%08d.png"),
        ]
        _run_logged(
            extract, label=f"extract-{chunk.index:05d}", log=log,
            timeout_seconds=timeout_minutes * 60, progress_probe=lambda: len(list(incoming.glob("*.png"))),
            stop_file=stop_file,
        )
        extracted = len(list(incoming.glob("*.png")))
        if extracted != chunk.source_frames:
            raise RecoveryError(f"Lote {chunk.index}: extraiu {extracted}/{chunk.source_frames} frames")

        frames, frame_directory = generate_rife_frames_safe(
            contract,
            incoming,
            outgoing,
            source_frames=chunk.source_frames,
            target_frames=chunk.target_frames,
            label=f"rife-{chunk.index:05d}",
            log=log,
            timeout_minutes=timeout_minutes,
            stop_file=stop_file,
        )
        first_number = int(frames[0].stem)
        partial_segment = contract.chunk_root / f"segment_{chunk.index:05d}.partial.mkv"
        final_segment = contract.chunk_root / f"segment_{chunk.index:05d}.mkv"
        merge = [
            str(contract.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
            "-framerate", f"{contract.target_fps:.8f}", "-start_number", str(first_number),
            "-i", str(frame_directory / "%08d.png"), "-map", "0:v:0", "-an",
            "-frames:v", str(len(frames)), "-c:v", "ffv1", "-level", "3", "-coder", "1",
            "-context", "1", "-g", "1", "-slicecrc", "1", "-pix_fmt", "yuv420p",
            "-threads", str(contract.cpu_threads), "-progress", "pipe:1", "-nostats", str(partial_segment),
        ]
        _run_logged(
            merge, label=f"segment-{chunk.index:05d}", log=log,
            timeout_seconds=timeout_minutes * 60, stop_file=stop_file,
        )
        _validate_video(
            ffprobe=contract.ffprobe, path=partial_segment, width=contract.target_width,
            height=contract.target_height, fps=contract.target_fps, codec="ffv1",
        )
        segment_quality = inspect_matroska_segment(partial_segment)
        if segment_quality.packet_count != len(frames):
            raise RecoveryError(
                f"Lote {chunk.index}: segmento tem {segment_quality.packet_count}/{len(frames)} pacotes"
            )
        if segment_quality.solid_black_frames:
            raise RecoveryError(
                f"Lote {chunk.index}: modo UHD produziu {segment_quality.solid_black_frames} quadros pretos"
            )
        os.replace(partial_segment, final_segment)
        _safe_rmtree_child(contract.chunk_root, incoming)
        if frame_directory != outgoing:
            _safe_rmtree_child(contract.chunk_root, frame_directory)
        _safe_rmtree_child(contract.chunk_root, outgoing)
        segments.append(final_segment)
        completed_source += chunk.source_frames
        completed_target += len(frames)
        _write_state(
            contract, phase="rife", completed_segments=len(segments),
            completed_source_frames=completed_source, completed_target_frames=completed_target,
            extra={"remaining_chunks": len(schedule) - position},
        )
        percent = 100.0 * completed_target / contract.total_target_frames
        log(f"COMMIT segment={chunk.index} progress={percent:.3f}% target={completed_target}/{contract.total_target_frames}")
    if completed_source != contract.total_source_frames or completed_target != contract.total_target_frames:
        raise RecoveryError(
            f"RIFE terminou fora do contrato: source={completed_source}/{contract.total_source_frames} "
            f"target={completed_target}/{contract.total_target_frames}"
        )
    log("BLACK_GATE_START final segment audit")
    total_black = 0
    for number, segment in enumerate(segments, start=1):
        quality = inspect_matroska_segment(segment)
        total_black += quality.solid_black_frames
        if number % 250 == 0 or number == len(segments):
            log(f"BLACK_GATE {number}/{len(segments)} black_frames={total_black}")
    if total_black:
        raise RecoveryError(f"Auditoria final encontrou {total_black} quadros pretos; codificacao bloqueada")
    log("BLACK_GATE_OK black_frames=0")
    return concatenate_master(contract, segments, log, timeout_minutes=timeout_minutes)


def _concat_line(path: Path) -> str:
    escaped = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
    return f"file '{escaped}'"


def concat_manifest(segments: list[Path], packet_counts: list[int], fps: float) -> str:
    """Build a concat manifest whose timeline is derived from frame counts.

    The short FFV1 Matroska segments use a 1 ms time base.  Letting FFmpeg infer
    every segment duration therefore accumulates sub-millisecond rounding over
    thousands of files.  Explicit durations keep the concatenated master on the
    exact CFR timeline without re-encoding any frame.
    """

    if len(segments) != len(packet_counts):
        raise ValueError("segments and packet_counts must have the same length")
    if fps <= 0:
        raise ValueError("fps must be positive")
    lines: list[str] = []
    for segment, packet_count in zip(segments, packet_counts, strict=True):
        if packet_count <= 0:
            raise ValueError(f"{segment.name}: packet count must be positive")
        lines.append(_concat_line(segment))
        lines.append(f"duration {packet_count / fps:.12f}")
    return "\n".join(lines) + "\n"


def concatenate_master(
    contract: RecoveryContract,
    segments: list[Path],
    log: Callable[[str], None],
    *,
    timeout_minutes: float,
) -> Path:
    if contract.master_path.is_file():
        info = _validate_video(
            ffprobe=contract.ffprobe, path=contract.master_path, width=contract.target_width,
            height=contract.target_height, fps=contract.target_fps, codec="ffv1",
            duration_minimum=contract.duration - 0.5,
        )
        if abs(_duration(info) - contract.duration) <= 0.5:
            log(f"MASTER_REUSE {contract.master_path} duration={_duration(info):.3f}s")
            return contract.master_path
        raise RecoveryError("Master de recuperacao existente nao cumpre o contrato")
    packet_counts: list[int] = []
    for number, segment in enumerate(segments, start=1):
        quality = inspect_matroska_segment(segment)
        if quality.solid_black_frames:
            raise RecoveryError(f"{segment.name}: quadros pretos reapareceram antes da montagem")
        packet_counts.append(quality.packet_count)
        if number % 500 == 0 or number == len(segments):
            log(f"TIMELINE_SCAN {number}/{len(segments)} packets={sum(packet_counts)}")
    if sum(packet_counts) != contract.total_target_frames:
        raise RecoveryError(
            f"Montagem recusada: {sum(packet_counts)} pacotes, esperados {contract.total_target_frames}"
        )

    concat_file = contract.job_dir / "recovery-concat-timed.txt"
    concat_file.write_text(concat_manifest(segments, packet_counts, contract.target_fps), encoding="utf-8")
    # Keep the first stream-copy attempt as evidence.  Its frames are intact,
    # but its timestamp line is short because Matroska rounded each segment.
    legacy_partial = contract.job_dir / "recovered_rife_master.partial.mkv"
    if legacy_partial.is_file():
        log(f"MASTER_PARTIAL_PRESERVED {legacy_partial} size={legacy_partial.stat().st_size}")
    partial = contract.job_dir / "recovered_rife_master.timeline-partial.mkv"
    command = [
        str(contract.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(concat_file), "-map", "0:v:0", "-an",
        "-c", "copy", "-t", f"{contract.duration:.6f}", "-progress", "pipe:1", "-nostats", str(partial),
    ]
    _run_logged(command, label="concat-master", log=log, timeout_seconds=max(3600, timeout_minutes * 60))
    info = _validate_video(
        ffprobe=contract.ffprobe, path=partial, width=contract.target_width,
        height=contract.target_height, fps=contract.target_fps, codec="ffv1",
        duration_minimum=contract.duration - 0.5,
    )
    if abs(_duration(info) - contract.duration) > 0.5:
        raise RecoveryError(f"Master concatenado tem duracao {_duration(info):.3f}s; esperado {contract.duration:.3f}s")
    os.replace(partial, contract.master_path)
    _write_state(
        contract, phase="master_ready", completed_segments=len(segments),
        completed_source_frames=contract.total_source_frames,
        completed_target_frames=contract.total_target_frames,
        extra={"master": str(contract.master_path), "master_size": contract.master_path.stat().st_size},
    )
    log(f"MASTER_COMMIT {contract.master_path} size={contract.master_path.stat().st_size}")
    return contract.master_path


def _final_filter(contract: RecoveryContract, color_plan: Any) -> str:
    return (
        f"scale={contract.target_width}:{contract.target_height}:force_original_aspect_ratio=increase:"
        "flags=lanczos+accurate_rnd+full_chroma_int,"
        f"crop={contract.target_width}:{contract.target_height},"
        f"format={color_plan.working_pix_fmt},{color_plan.setparams_filter()}"
    )


def without_faststart(arguments: list[str]) -> list[str]:
    """Remove MP4 fast-start relocation while preserving other muxer flags."""

    cleaned: list[str] = []
    index = 0
    while index < len(arguments):
        if arguments[index] == "-movflags" and index + 1 < len(arguments):
            flags = arguments[index + 1].replace("+faststart", "")
            if flags:
                cleaned.extend((arguments[index], flags))
            index += 2
            continue
        cleaned.append(arguments[index])
        index += 1
    return cleaned


def _final_command(contract: RecoveryContract, master: Path, destination: Path, *, duration: float) -> tuple[list[str], Any, Any]:
    source_info = _probe(contract.ffprobe, contract.source)
    source_color = ColorProfile.from_probe(source_info)
    color_plan = build_color_pipeline(
        source_color, effects_active=False, transition_active=False,
        enhancement_mode="realesrgan", rife_active=True,
    )
    encoders = detect_ffmpeg_encoders(str(contract.ffmpeg))
    delivery = build_delivery_plan(
        output=contract.output, profile=PROFILE_AUTO, color_plan=color_plan,
        width=contract.target_width, height=contract.target_height, fps=contract.target_fps,
        preview=False, use_cpu=False, nvenc_available="hevc_nvenc" in encoders,
        available_encoders=encoders,
    )
    if delivery.blocking:
        raise RecoveryError("Contrato de entrega bloqueado: " + " | ".join(delivery.errors))
    bitrate_mbps = max(8, min(600, round(12 * contract.target_width * contract.target_height / (1920 * 1080) * max(1, contract.target_fps / 60))))
    command = [
        str(contract.ffmpeg), "-y", "-hide_banner", "-nostdin", "-loglevel", "error",
        "-i", str(master), "-i", str(contract.source), "-map", "0:v:0", "-map", "1:a:0",
        "-vf", _final_filter(contract, color_plan),
    ]
    command += delivery.video_args(
        use_cpu=False, nvenc_available="hevc_nvenc" in encoders,
        bitrate_mbps=bitrate_mbps, fps=round(contract.target_fps),
    )
    command += color_plan.metadata_args(output=True)
    command += delivery.audio_args()
    command += ["-threads", str(contract.cpu_threads), "-t", f"{duration:.6f}"]
    # This is a local 30+ GiB deliverable.  Relocating the MP4 index to the
    # beginning adds a second full-file pass and failed on the external target.
    # Keeping the index at the end is fully playable and does not affect quality.
    command += without_faststart(delivery.muxer_args())
    # Persist progress instead of sending it through the Python stdout pipe.
    # If the controlling process is closed, FFmpeg can still flush the MP4
    # trailer and a later recovery run can validate/promote the completed file.
    progress_url = str((contract.history_dir / "final-encode-progress.log").resolve())
    command += ["-progress", progress_url, "-nostats", str(destination)]
    return command, color_plan, delivery


def self_test(contract: RecoveryContract, log: Callable[[str], None], *, timeout_minutes: float) -> Path:
    segments, _completed_target = validate_contract(contract, log, full_scan=False)
    if not segments:
        raise RecoveryError("Nenhum segmento existente para o autoteste")
    destination = contract.job_dir / "recovery-self-test.mp4"
    command, _color, _delivery = _final_command(contract, segments[0], destination, duration=0.10)
    _run_logged(command, label="final-encoder-self-test", log=log, timeout_seconds=timeout_minutes * 60)
    info = _validate_video(
        ffprobe=contract.ffprobe, path=destination, width=contract.target_width,
        height=contract.target_height, fps=contract.target_fps, codec="hevc",
    )
    if not any(stream.get("codec_type") == "audio" for stream in info.get("streams", [])):
        raise RecoveryError("Autoteste final nao preservou audio")
    log(f"SELF_TEST_OK {destination} size={destination.stat().st_size}")
    return destination


def finalize(contract: RecoveryContract, master: Path, log: Callable[[str], None], *, timeout_minutes: float) -> Path:
    contract.output.parent.mkdir(parents=True, exist_ok=True)
    staged_master = contract.output.with_name(f".{contract.output.stem}.recovery-master.mkv")
    if staged_master.is_file():
        staged_info = _validate_video(
            ffprobe=contract.ffprobe, path=staged_master, width=contract.target_width,
            height=contract.target_height, fps=contract.target_fps, codec="ffv1",
            duration_minimum=contract.duration - 0.5,
        )
        if abs(_duration(staged_info) - contract.duration) > 0.5:
            raise RecoveryError(
                f"Master local tem duracao {_duration(staged_info):.3f}s; esperada {contract.duration:.3f}s"
            )
        master = staged_master
        log(f"MASTER_LOCAL_REUSE {master} duration={_duration(staged_info):.3f}s")
    partial = contract.output.with_name(f".{contract.output.stem}.recovery-partial{contract.output.suffix}")
    command, _color, delivery = _final_command(contract, master, partial, duration=contract.duration)
    expectation = VerifyExpectation(
        width=contract.target_width, height=contract.target_height, fps=contract.target_fps,
        duration=contract.duration, expect_audio=True, video_codec=delivery.video_codec,
        audio_codec=delivery.audio_codec, audio_channels=2, audio_sample_rate=48000,
    )
    verification = None
    if partial.is_file():
        log(f"PARTIAL_REUSE_CHECK {partial} size={partial.stat().st_size}")
        try:
            candidate = quick_verify(str(contract.ffprobe), partial, expectation)
        except Exception as exc:
            candidate = None
            details = f"{type(exc).__name__}: {exc}"
        else:
            details = " | ".join(f"{issue.code}: {issue.message}" for issue in candidate.errors)
        if candidate is not None and candidate.passed:
            verification = candidate
            log("PARTIAL_REUSE_OK completed orphan encode accepted")
        else:
            rejected = partial.with_name(f"{partial.stem}.rejected-{int(time.time())}{partial.suffix}")
            os.replace(partial, rejected)
            log(f"PARTIAL_REUSE_REJECTED preserved={rejected} details={details}")
    if verification is None:
        _write_state(
            contract, phase="final_encoding", completed_segments=len(contiguous_segments(contract.chunk_root)),
            completed_source_frames=contract.total_source_frames, completed_target_frames=contract.total_target_frames,
            extra={"partial_output": str(partial)},
        )
        _run_logged(command, label="final-encode", log=log, timeout_seconds=max(43200, timeout_minutes * 60))
        log("VERIFY_START quick contract + frame count")
        verification = quick_verify(str(contract.ffprobe), partial, expectation)
    _atomic_json(contract.result_path, {"schema": 1, "job_id": contract.job_id, "verification": verification.to_dict()})
    if not verification.passed:
        details = " | ".join(f"{issue.code}: {issue.message}" for issue in verification.errors)
        raise RecoveryError("Verificacao final falhou: " + details)
    backup = contract.output.with_name(f".{contract.output.name}.previous")
    backup.unlink(missing_ok=True)
    if contract.output.exists():
        os.replace(contract.output, backup)
    try:
        os.replace(partial, contract.output)
    except BaseException:
        if backup.exists() and not contract.output.exists():
            os.replace(backup, contract.output)
        raise
    backup.unlink(missing_ok=True)
    job_path = contract.history_dir / "job.json"
    job = _load_json(job_path)
    job.update({
        "status": "success", "finished_at": time.time(), "output": str(contract.output),
        "error": "", "recovered": True, "recovery_result": str(contract.result_path),
    })
    _atomic_json(job_path, job)
    _write_state(
        contract, phase="complete", completed_segments=len(contiguous_segments(contract.chunk_root)),
        completed_source_frames=contract.total_source_frames, completed_target_frames=contract.total_target_frames,
        extra={"output": str(contract.output), "output_size": contract.output.stat().st_size,
               "verification": verification.to_dict()},
    )
    log(f"RECOVERY_COMPLETE output={contract.output} size={contract.output.stat().st_size}")
    return contract.output


def _space_check(contract: RecoveryContract, segments: list[Path]) -> dict[str, float]:
    sample_bytes = sum(item.stat().st_size for item in segments)
    average = sample_bytes / max(1, len(segments))
    source_counts = source_chunk_counts(contract.total_source_frames, contract.chunk_frames)
    remaining_segments = max(0, len(source_counts) - len(segments))
    projected_segments = average * len(source_counts)
    scratch_required = max(0.0, projected_segments - sample_bytes) + projected_segments + 20 * 1024 ** 3
    output_required = 50 * 1024 ** 3
    scratch_free = shutil.disk_usage(contract.job_dir).free
    output_free = shutil.disk_usage(contract.output.parent).free
    if scratch_free < scratch_required:
        raise RecoveryError(
            f"Espaco scratch insuficiente: livre={scratch_free / 1024**3:.1f} GiB, "
            f"estimado={scratch_required / 1024**3:.1f} GiB"
        )
    if output_free < output_required:
        raise RecoveryError(f"Espaco de saida insuficiente: {output_free / 1024**3:.1f} GiB")
    return {
        "remaining_segments": float(remaining_segments),
        "scratch_free_gib": scratch_free / 1024 ** 3,
        "scratch_required_gib": scratch_required / 1024 ** 3,
        "output_free_gib": output_free / 1024 ** 3,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Retoma um render RIFE Phase 6 interrompido sem descartar segmentos")
    parser.add_argument("action", choices=("validate", "self-test", "resume"))
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--history-dir", required=True)
    parser.add_argument("--chunk-root", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--source")
    parser.add_argument("--output")
    parser.add_argument("--timeout-minutes", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    contract = load_contract(args)
    logger = RecoveryLogger(contract.log_path)
    try:
        logger(f"RECOVERY_START action={args.action} job={contract.job_id}")
        segments, completed_target = validate_contract(contract, logger, full_scan=args.action != "self-test")
        space = _space_check(contract, segments)
        logger("SPACE_OK " + " ".join(f"{key}={value:.1f}" for key, value in space.items()))
        if args.action == "validate":
            source_counts = source_chunk_counts(contract.total_source_frames, contract.chunk_frames)
            completed_source = sum(source_counts[:len(segments)])
            _write_state(
                contract, phase="validated", completed_segments=len(segments),
                completed_source_frames=completed_source, completed_target_frames=completed_target,
                extra={"space": space},
            )
            logger("VALIDATION_COMPLETE")
            return 0
        if args.action == "self-test":
            self_test(contract, logger, timeout_minutes=args.timeout_minutes)
            return 0
        # resume_rife performs a fresh full validation before any mutation.
        master = resume_rife(contract, logger, timeout_minutes=args.timeout_minutes)
        finalize(contract, master, logger, timeout_minutes=args.timeout_minutes)
        return 0
    except KeyboardInterrupt:
        logger("RECOVERY_STOPPED graceful interruption; committed segments remain resumable")
        return 130
    except Exception as exc:
        logger(f"RECOVERY_FAILED {type(exc).__name__}: {exc}")
        return 1
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
