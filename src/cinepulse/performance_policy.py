"""Hardware utilization policy for CinePulse Preview.

Phase 2 turns the Phase 1 measurements into explicit resource budgets without
changing image-quality contracts.  The policy is intentionally small and
pure so UI code, render planning and physical benchmark tooling can share the
same decisions.
"""

from __future__ import annotations

from dataclasses import dataclass


PROFILE_BALANCED = "Equilibrado"
PROFILE_DEDICATED = "Máquina dedicada"
PROFILE_OVERNIGHT = "Overnight — máximo"
MACHINE_PROFILES = (PROFILE_BALANCED, PROFILE_DEDICATED, PROFILE_OVERNIGHT)
FULL_UTILIZATION = True


@dataclass(frozen=True)
class MachineBudget:
    profile: str
    logical_threads: int
    cpu_threads: int
    reserved_threads: int
    realesrgan_pipeline: str

    @property
    def utilization_percent(self) -> int:
        if self.logical_threads <= 0:
            return 100
        return int(round(self.cpu_threads / self.logical_threads * 100.0))


def _logical_threads(value: int | None) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def clamp_cpu_threads(requested: int | None, logical_threads: int | None) -> int:
    """Clamp a user/runtime request to the hardware's logical CPU envelope."""
    logical = _logical_threads(logical_threads)
    try:
        value = int(requested or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(logical, value))


def profile_cpu_threads(profile: str, logical_threads: int | None) -> int:
    """Use the complete logical CPU envelope.

    CinePulse 1.2.4 intentionally stops reserving CPU headroom by profile.
    Profiles remain accepted for project/UI compatibility, but scheduling is
    full-utilization-first: every render may use every logical CPU.
    """
    return _logical_threads(logical_threads)


def default_cpu_threads(logical_threads: int | None) -> int:
    return profile_cpu_threads(PROFILE_BALANCED, logical_threads)


def profile_for_threads(requested: int | None, logical_threads: int | None) -> str:
    """Describe a thread request under full-utilization scheduling."""
    logical = _logical_threads(logical_threads)
    value = clamp_cpu_threads(requested, logical)
    return PROFILE_OVERNIGHT if value == logical else "Manual"


def realesrgan_live_process_cap(
    vram_mb: int | None,
    *,
    vram_free_mb: float | int | None,
    width: int = 1920,
    height: int = 1080,
) -> int:
    """Return the fixed maximum Real-ESRGAN process envelope for the adapter.

    Live free-VRAM and geometry are intentionally ignored. 1.2.4 starts from
    maximum static concurrency and relies on an actual runtime failure/OOM to
    trigger a lower-pressure retry instead of pre-emptively throttling.
    """
    del vram_free_mb, width, height
    total = max(0, int(vram_mb or 0))
    if total >= 20_000:
        return 4
    if total >= 7_500:
        return 3
    if total >= 4_000:
        return 2
    return 1


def realesrgan_pipeline_threads(
    cpu_threads: int | None,
    logical_threads: int | None,
    vram_mb: int | None = None,
    *,
    vram_free_mb: float | int | None = None,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Build the full-utilization Real-ESRGAN NCNN -j budget.

    Requested CPU headroom and live VRAM are not used to throttle the render.
    Load/save workers use the host envelope and GPU workers use the fixed
    adapter-size ceiling. Runtime failure handling remains responsible for
    retrying at lower pressure when the aggressive first attempt cannot run.
    """
    del cpu_threads
    logical = _logical_threads(logical_threads)
    io_workers = max(1, min(4, logical))
    gpu_workers = realesrgan_live_process_cap(
        vram_mb,
        vram_free_mb=vram_free_mb,
        width=width,
        height=height,
    )
    return f"{io_workers}:{gpu_workers}:{io_workers}"


def machine_budget(profile: str, logical_threads: int | None, vram_mb: int | None = None) -> MachineBudget:
    logical = _logical_threads(logical_threads)
    cpu_threads = logical
    return MachineBudget(
        profile=profile if profile in MACHINE_PROFILES else PROFILE_OVERNIGHT,
        logical_threads=logical,
        cpu_threads=cpu_threads,
        reserved_threads=0,
        realesrgan_pipeline=realesrgan_pipeline_threads(cpu_threads, logical, vram_mb),
    )
