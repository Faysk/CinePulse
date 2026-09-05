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
    """Return the CPU budget for a named machine profile.

    Balanced keeps enough headroom for the desktop/OS. Dedicated leaves two
    logical CPUs free on machines large enough to benefit. Overnight uses the
    complete logical CPU envelope and is intended for unattended renders.
    """
    logical = _logical_threads(logical_threads)
    name = str(profile or PROFILE_BALANCED)
    if name == PROFILE_OVERNIGHT:
        return logical
    if name == PROFILE_DEDICATED:
        reserve = 2 if logical >= 8 else 1 if logical >= 3 else 0
        return max(1, logical - reserve)
    return max(1, min(logical, int(round(logical * 0.60))))


def default_cpu_threads(logical_threads: int | None) -> int:
    return profile_cpu_threads(PROFILE_BALANCED, logical_threads)


def profile_for_threads(requested: int | None, logical_threads: int | None) -> str:
    """Describe an existing thread count using the closest explicit profile."""
    logical = _logical_threads(logical_threads)
    value = clamp_cpu_threads(requested, logical)
    exact = {
        profile_cpu_threads(PROFILE_BALANCED, logical): PROFILE_BALANCED,
        profile_cpu_threads(PROFILE_DEDICATED, logical): PROFILE_DEDICATED,
        profile_cpu_threads(PROFILE_OVERNIGHT, logical): PROFILE_OVERNIGHT,
    }
    return exact.get(value, "Manual")


def realesrgan_pipeline_threads(
    cpu_threads: int | None,
    logical_threads: int | None,
    vram_mb: int | None = None,
) -> str:
    """Build the Real-ESRGAN NCNN ``-j load:proc:save`` budget.

    Phase 2 deliberately scales CPU-side image feeding/saving more aggressively
    than GPU processing.  Extra ``proc`` workers can duplicate Vulkan working
    sets, so cards below 10 GB VRAM stay at two GPU workers until physical
    telemetry proves a larger value safe.
    """
    logical = _logical_threads(logical_threads)
    threads = clamp_cpu_threads(cpu_threads, logical)
    ratio = threads / logical

    if threads <= 4:
        io_workers = 1
    elif ratio < 0.75:
        io_workers = 2
    elif ratio < 0.95:
        io_workers = 3
    else:
        io_workers = 4

    memory = max(0, int(vram_mb or 0))
    if memory >= 20_000 and threads >= 12:
        gpu_workers = 4
    elif memory >= 10_000 and threads >= 8:
        gpu_workers = 3
    else:
        gpu_workers = 2 if threads >= 4 else 1

    return f"{io_workers}:{gpu_workers}:{io_workers}"


def machine_budget(profile: str, logical_threads: int | None, vram_mb: int | None = None) -> MachineBudget:
    logical = _logical_threads(logical_threads)
    cpu_threads = profile_cpu_threads(profile, logical)
    return MachineBudget(
        profile=profile if profile in MACHINE_PROFILES else PROFILE_BALANCED,
        logical_threads=logical,
        cpu_threads=cpu_threads,
        reserved_threads=max(0, logical - cpu_threads),
        realesrgan_pipeline=realesrgan_pipeline_threads(cpu_threads, logical, vram_mb),
    )
