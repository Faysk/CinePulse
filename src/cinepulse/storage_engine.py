"""Storage planning, scratch policy and bounded cache/chunk helpers.

Core Integrity Phase 6 makes storage a first-class render contract.  The
estimator derives its stages from RenderPlan, neural frame materialization is
bounded by chunk worksets, scratch can live on a separate volume, and cache
retention is controlled by a quota/LRU policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import time
from typing import Iterable

from .render_plan import FrameSpec, RenderPlan

GIB = 1024 ** 3
DEFAULT_CACHE_QUOTA_GB = 50.0
DEFAULT_CHUNK_BUDGET_GB = 4.0
MIN_CHUNK_FRAMES = 2
MAX_CHUNK_FRAMES = 240


@dataclass(frozen=True)
class StorageStageEstimate:
    key: str
    title: str
    persistent_gb: float
    working_set_gb: float
    peak_scratch_gb: float
    duration_seconds: float
    detail: str

    def line(self) -> str:
        return (
            f"{self.title}: persistente ~{self.persistent_gb:.2f} GB • "
            f"workset ~{self.working_set_gb:.2f} GB • pico ~{self.peak_scratch_gb:.2f} GB • "
            f"duração materializada ~{self.duration_seconds:.1f}s — {self.detail}"
        )


@dataclass(frozen=True)
class StorageEstimate:
    output_gb: float
    peak_scratch_gb: float
    persistent_scratch_gb: float
    cache_growth_gb: float
    stages: tuple[StorageStageEstimate, ...]
    ai_chunk_frames: int
    rife_chunk_frames: int
    clip_duration_seconds: float = 0.0
    project_duration_seconds: float = 0.0
    architecture_version: str = "core-integrity-phase6-storage-engine-stage-duration-v2"

    @property
    def temporary_gb(self) -> float:
        """Compatibility name used by older preflight/UI code."""
        return self.peak_scratch_gb


@dataclass(frozen=True)
class CachePruneResult:
    before_bytes: int
    after_bytes: int
    removed_bytes: int
    removed_files: int
    quota_bytes: int

    @property
    def before_gb(self) -> float:
        return self.before_bytes / GIB

    @property
    def after_gb(self) -> float:
        return self.after_bytes / GIB

    @property
    def removed_gb(self) -> float:
        return self.removed_bytes / GIB


def resolve_scratch_dir(value: str | Path | None, default: Path) -> Path:
    text = str(value or "").strip()
    return Path(text).expanduser().resolve(strict=False) if text else default.expanduser().resolve(strict=False)


def cache_usage_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _protected(path: Path, protected: set[Path]) -> bool:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path.absolute()
    return resolved in protected


def enforce_cache_quota(
    root: Path,
    quota_gb: float,
    *,
    protected: Iterable[Path] = (),
) -> CachePruneResult:
    """Prune oldest cache files until total size is within the quota.

    Recency uses max(atime, mtime); callers touch cache hits so this remains
    meaningful even on systems where atime updates are disabled.  Protected
    files are never deleted during the current job.
    """

    quota_bytes = max(0, int(float(quota_gb) * GIB))
    root.mkdir(parents=True, exist_ok=True)
    protected_set = {Path(item).resolve(strict=False) for item in protected}
    entries: list[tuple[float, Path, int]] = []
    before = 0
    for path in root.rglob("*"):
        try:
            if not path.is_file() or path.is_symlink():
                continue
            stat = path.stat()
        except OSError:
            continue
        before += stat.st_size
        if not _protected(path, protected_set):
            entries.append((max(stat.st_atime, stat.st_mtime), path, stat.st_size))

    current = before
    removed_bytes = 0
    removed_files = 0
    for _stamp, path, size in sorted(entries, key=lambda item: item[0]):
        if current <= quota_bytes:
            break
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue
        current -= size
        removed_bytes += size
        removed_files += 1

    # Best-effort removal of empty cache subdirectories only.
    directories = sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            pass

    return CachePruneResult(
        before_bytes=before,
        after_bytes=max(0, current),
        removed_bytes=removed_bytes,
        removed_files=removed_files,
        quota_bytes=quota_bytes,
    )


def touch_cache_entry(path: Path) -> None:
    try:
        now = time.time()
        os.utime(path, (now, now))
    except OSError:
        pass


def _frame_working_bytes(spec: FrameSpec, *, rgba: bool = True) -> int:
    channels = 4 if rgba else 3
    bytes_per_channel = 2 if "10" in spec.pixel_format or "12" in spec.pixel_format or "16" in spec.pixel_format else 1
    return max(1, spec.width) * max(1, spec.height) * channels * bytes_per_channel


def choose_chunk_frames(
    input_spec: FrameSpec,
    output_spec: FrameSpec,
    *,
    budget_gb: float = DEFAULT_CHUNK_BUDGET_GB,
    output_frames_per_input: float = 1.0,
    minimum: int = MIN_CHUNK_FRAMES,
    maximum: int = MAX_CHUNK_FRAMES,
) -> int:
    """Choose a bounded materialized-frame chunk from a scratch workset budget."""

    budget_bytes = max(64 * 1024 * 1024, float(budget_gb) * GIB)
    per_input = _frame_working_bytes(input_spec)
    per_output = _frame_working_bytes(output_spec) * max(1.0, float(output_frames_per_input))
    # Incoming PNG + outgoing PNG + filesystem/encoder headroom.
    per_unit = max(1, int((per_input + per_output) * 1.20))
    frames = int(budget_bytes // per_unit)
    return max(minimum, min(maximum, frames))


def _compressed_gb(spec: FrameSpec, duration: float, *, lossless: bool) -> float:
    seconds = max(0.0, float(duration))
    if seconds <= 0:
        return 0.0
    # Conservative planning model. Lossless FFV1 is estimated from raw YUV,
    # while lossy intermediates use a target-bitrate-like pixel/fps heuristic.
    if lossless:
        bit_depth_factor = 2.0 if "10" in spec.pixel_format else 1.0
        raw = spec.width * spec.height * max(1.0, spec.fps) * seconds * 1.5 * bit_depth_factor
        return raw * 0.42 / GIB
    pixels_ratio = spec.width * spec.height / (1920 * 1080)
    mbps = max(8.0, min(600.0, 12.0 * pixels_ratio * max(1.0, spec.fps / 60.0)))
    return mbps * seconds / 8 / 1024


def _neural_chunk_gb(
    source: FrameSpec,
    target: FrameSpec,
    chunk_frames: int,
    *,
    output_frames_per_input: float = 1.0,
) -> float:
    incoming = _frame_working_bytes(source) * chunk_frames
    outgoing = _frame_working_bytes(target) * chunk_frames * max(1.0, output_frames_per_input)
    return (incoming + outgoing) * 1.20 / GIB


def estimate_storage(
    plan: RenderPlan,
    *,
    output_gb: float,
    duration: float | None = None,
    clip_duration: float | None = None,
    project_duration: float | None = None,
    cache_current_gb: float = 0.0,
    cache_quota_gb: float = DEFAULT_CACHE_QUOTA_GB,
    chunk_budget_gb: float = DEFAULT_CHUNK_BUDGET_GB,
) -> StorageEstimate:
    """Estimate scratch/cache pressure from the durations each stage materializes.

    ``clip_duration`` is the duration of the reusable visual clip before a music
    loop is expanded. ``project_duration`` is the final timeline duration (for
    example the music length).  The legacy ``duration`` argument remains as a
    compatibility fallback and maps to both values.

    In music mode the expensive pre-loop stages (color prepass, Real-ESRGAN,
    master and loop transition) operate on the reusable clip only.  VFX, final
    RIFE and delivery operate on the expanded project timeline.  Treating every
    stage as project-long was the 1.1.2 false-terabyte preflight bug.
    """

    if project_duration is None:
        project_duration = duration
    if clip_duration is None:
        clip_duration = duration if duration is not None else project_duration
    if project_duration is None or clip_duration is None:
        raise TypeError("estimate_storage requires duration or both clip_duration/project_duration")

    clip_seconds = max(0.01, float(clip_duration))
    project_seconds = max(0.01, float(project_duration))
    # Original-video projects have one timeline.  Keeping this normalization
    # here prevents an accidental caller mismatch from under-estimating stages.
    if plan.project_mode != "music":
        clip_seconds = project_seconds

    def stage_duration(key: str) -> float:
        if plan.project_mode == "music" and key in {"color", "enhancement", "rife_base", "master", "transition"}:
            return clip_seconds
        return project_seconds

    stages: list[StorageStageEstimate] = []
    current_persistent = 0.0
    peak = 0.0
    cache_growth = 0.0

    ai = plan.step("enhancement")
    rife_base = plan.step("rife_base")
    rife = plan.step("rife_final")
    color = plan.step("color")
    ai_will_attempt = ai.attempts and plan.enhancement_mode == "realesrgan"
    rife_final_will_attempt = rife.attempts and plan.interpolation_mode == "rife"
    color_prepass = color.runs and (
        ai_will_attempt
        or rife_base.runs
        or (rife_final_will_attempt and not plan.needs_master)
    )

    # The worker materializes an explicit lossless color prepass only when a
    # neural stage is the first consumer.  Otherwise color conversion is fused
    # into the master/final filter and does not create a separate scratch file.
    if color_prepass and color.output_spec is not None:
        seconds = stage_duration("color")
        converted = _compressed_gb(color.output_spec, seconds, lossless=True)
        stage_peak = current_persistent + converted
        stages.append(StorageStageEstimate(
            "color", "Gerenciamento de cor", converted, converted, stage_peak, seconds,
            "prepass lossless explícito antes do primeiro estágio neural.",
        ))
        current_persistent = converted
        peak = max(peak, stage_peak)

    ai_chunk = MAX_CHUNK_FRAMES
    if ai.attempts and ai.input_spec and ai.output_spec and ai.materializes_frames:
        seconds = stage_duration("enhancement")
        ai_chunk = choose_chunk_frames(ai.input_spec, ai.output_spec, budget_gb=chunk_budget_gb)
        working = _neural_chunk_gb(ai.input_spec, ai.output_spec, ai_chunk)
        enhanced = _compressed_gb(ai.output_spec, seconds, lossless=True)
        # Chunk videos coexist with the assembled cache only during concat.
        # A color prepass, when present, also remains live until AI promotion.
        stage_peak = max(current_persistent + working, current_persistent + enhanced * 2.05)
        cache_growth = min(enhanced, cache_quota_gb) if cache_quota_gb > 0 else 0.0
        stages.append(StorageStageEstimate(
            "enhancement", "Real-ESRGAN em chunks", 0.0, working, stage_peak, seconds,
            f"{ai_chunk} quadro(s)/lote; PNGs são descartados e o master (~{enhanced:.2f} GB) é promovido ao cache.",
        ))
        # The assembled AI master is atomically moved to cache and the optional
        # color prepass is released by the worker after successful promotion.
        current_persistent = 0.0
        peak = max(peak, stage_peak)

    rife_chunk = MAX_CHUNK_FRAMES
    if rife_base.runs and rife_base.input_spec and rife_base.output_spec and rife_base.materializes_frames:
        seconds = stage_duration("rife_base")
        ratio = rife_base.output_spec.fps / max(1.0, rife_base.input_spec.fps)
        rife_chunk = choose_chunk_frames(
            rife_base.input_spec, rife_base.output_spec, budget_gb=chunk_budget_gb,
            output_frames_per_input=ratio,
        )
        working = _neural_chunk_gb(
            rife_base.input_spec, rife_base.output_spec, rife_chunk,
            output_frames_per_input=ratio,
        )
        interpolated = _compressed_gb(rife_base.output_spec, seconds, lossless=True)
        stage_peak = max(current_persistent + working, current_persistent + interpolated * 2.05)
        stages.append(StorageStageEstimate(
            "rife_base", "RIFE do clipe reutilizável", interpolated, working, stage_peak, seconds,
            f"{rife_chunk} quadro(s) fonte/lote; o master neural cobre apenas o clipe reutilizável.",
        ))
        current_persistent = interpolated
        peak = max(peak, stage_peak)

    for key in ("master", "transition", "vfx"):
        step = plan.step(key)
        if not step.runs or step.output_spec is None:
            continue
        seconds = stage_duration(key)
        produced = _compressed_gb(step.output_spec, seconds, lossless=not step.lossy_intermediate)
        # During production, previous visual source and new file overlap. Once
        # the stage succeeds the worker releases the consumed scratch source.
        stage_peak = current_persistent + produced
        stages.append(StorageStageEstimate(
            key, step.title, produced, produced, stage_peak, seconds,
            "intermediário anterior é liberado após a promoção desta etapa.",
        ))
        current_persistent = produced
        peak = max(peak, stage_peak)

    if rife.attempts and rife.input_spec and rife.output_spec and rife.materializes_frames:
        seconds = stage_duration("rife_final")
        ratio = rife.output_spec.fps / max(1.0, rife.input_spec.fps)
        rife_chunk = choose_chunk_frames(
            rife.input_spec, rife.output_spec, budget_gb=chunk_budget_gb,
            output_frames_per_input=ratio,
        )
        working = _neural_chunk_gb(
            rife.input_spec, rife.output_spec, rife_chunk,
            output_frames_per_input=ratio,
        )
        interpolated = _compressed_gb(rife.output_spec, seconds, lossless=True)
        stage_peak = max(current_persistent + working, current_persistent + interpolated * 2.05)
        stages.append(StorageStageEstimate(
            "rife_final", "RIFE em chunks", interpolated, working, stage_peak, seconds,
            f"{rife_chunk} quadro(s) fonte/lote; entrada/saída PNG não cobrem mais o projeto inteiro.",
        ))
        current_persistent = interpolated
        peak = max(peak, stage_peak)

    # Final encoding overlaps the latest visual intermediate with the partial
    # output, but the partial file belongs to the output volume.
    final_seconds = stage_duration("finalize")
    stages.append(StorageStageEstimate(
        "finalize", "Codificação final", current_persistent, 0.0, current_persistent, final_seconds,
        f"arquivo parcial de saída estimado separadamente em ~{max(0.0, output_gb):.2f} GB.",
    ))
    peak = max(peak, current_persistent)

    return StorageEstimate(
        output_gb=max(0.0, float(output_gb)),
        peak_scratch_gb=max(0.25, peak),
        persistent_scratch_gb=current_persistent,
        cache_growth_gb=max(0.0, cache_growth),
        stages=tuple(stages),
        ai_chunk_frames=ai_chunk,
        rife_chunk_frames=rife_chunk,
        clip_duration_seconds=clip_seconds,
        project_duration_seconds=project_seconds,
    )


def safe_rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass

@dataclass(frozen=True)
class ScratchProbe:
    path: Path
    volume: str
    free_gb: float
    total_gb: float
    write_mbps: float | None


_speed_probe_cache: dict[str, tuple[float, float | None]] = {}


def probe_scratch(path: Path, *, sample_mb: int = 8, cache_seconds: float = 900.0) -> ScratchProbe:
    """Return volume/free-space data plus a tiny cached sequential-write probe.

    The speed sample is intentionally small and labeled as indicative in the UI;
    it is used to distinguish obviously slow scratch locations, not as a formal
    disk benchmark.
    """

    root = path.expanduser().resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root)
    if os.name == "nt":
        volume = (root.drive or root.anchor or str(root)).upper()
    else:
        try:
            volume = f"dev:{root.stat().st_dev}"
        except OSError:
            volume = str(root.anchor or "/")
    now = time.monotonic()
    cached = _speed_probe_cache.get(volume)
    speed: float | None
    if cached and now - cached[0] <= cache_seconds:
        speed = cached[1]
    else:
        speed = None
        probe = root / f".cinepulse-speed-{os.getpid()}-{time.time_ns()}.tmp"
        payload = b"\0" * (1024 * 1024)
        try:
            start = time.perf_counter()
            with probe.open("wb", buffering=0) as handle:
                for _ in range(max(1, int(sample_mb))):
                    handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            elapsed = max(0.001, time.perf_counter() - start)
            speed = max(0.0, float(sample_mb) / elapsed)
        except OSError:
            speed = None
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
        _speed_probe_cache[volume] = (now, speed)
    return ScratchProbe(
        path=root,
        volume=volume,
        free_gb=usage.free / GIB,
        total_gb=usage.total / GIB,
        write_mbps=speed,
    )
