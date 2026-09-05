from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import asdict, dataclass
from typing import Iterable, Literal


MachineMode = Literal["balanced", "dedicated"]
StageKind = Literal[
    "decode",
    "color",
    "scale",
    "encode",
    "audio",
    "vfx_cpu",
    "neural_gpu",
    "neural_cpu",
    "verification",
    "other",
]

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class CpuTopology:
    logical_cpus: int
    physical_cores: int
    source: str = "fallback"

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CpuSchedule:
    stage: StageKind
    mode: MachineMode
    threads: int
    logical_cpus: int
    physical_cores: int
    reserve_logical: int
    reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _linux_physical_cores() -> int | None:
    try:
        text = open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    pairs: set[tuple[str, str]] = set()
    physical = core = None
    for line in text.splitlines() + [""]:
        if not line.strip():
            if physical is not None and core is not None:
                pairs.add((physical, core))
            physical = core = None
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "physical id":
            physical = value
        elif key == "core id":
            core = value
    return len(pairs) or None


def _windows_physical_cores() -> int | None:
    commands = (
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", "(Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum"],
        ["wmic", "cpu", "get", "NumberOfCores", "/value"],
    )
    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        values = [int(value) for value in re.findall(r"\d+", result.stdout)]
        if values:
            # PowerShell returns one aggregate. WMIC may return one value per socket.
            return values[0] if len(values) == 1 else sum(values)
    return None


def detect_cpu_topology() -> CpuTopology:
    logical = max(1, os.cpu_count() or 1)
    physical: int | None = None
    source = "logical-fallback"
    system = platform.system().lower()
    if system == "linux":
        physical = _linux_physical_cores()
        source = "proc-cpuinfo" if physical else source
    elif system == "windows":
        physical = _windows_physical_cores()
        source = "win32-processor" if physical else source
    if not physical or physical < 1 or physical > logical:
        # SMT is commonly 2-way; using ceil(logical/2) is safer than pretending
        # every logical processor is a full core when physical topology is hidden.
        physical = max(1, (logical + 1) // 2) if logical > 2 else logical
    return CpuTopology(logical_cpus=logical, physical_cores=physical, source=source)


def _reserve_threads(topology: CpuTopology, mode: MachineMode) -> int:
    logical = topology.logical_cpus
    if logical <= 4:
        return 1 if mode == "balanced" else 0
    if mode == "dedicated":
        # Dedicated is still not Realtime/"take the whole machine" mode. Keep a
        # little breathing room on larger CPUs for driver, I/O and UI work.
        return 1 if logical >= 12 else 0
    return max(1, min(4, round(logical * 0.15)))


def schedule_cpu_threads(
    stage: StageKind,
    *,
    topology: CpuTopology | None = None,
    mode: MachineMode = "balanced",
    gpu_active: bool = False,
    thermal_constrained: bool = False,
) -> CpuSchedule:
    if mode not in {"balanced", "dedicated"}:
        raise ValueError(f"Unsupported machine mode: {mode}")
    topology = topology or detect_cpu_topology()
    logical = max(1, topology.logical_cpus)
    physical = max(1, min(topology.physical_cores, logical))
    reserve = _reserve_threads(topology, mode)
    available = max(1, logical - reserve)

    if stage == "neural_gpu":
        # NCNN/Vulkan is GPU-bound. CPU mainly feeds image I/O; excessive host
        # threads can steal package power from a laptop GPU with no quality gain.
        target = min(available, max(2, min(physical, 6)))
        reason = "GPU neural stage keeps host concurrency modest to protect shared thermal/power budget"
    elif stage in {"decode", "audio", "verification"}:
        target = min(available, max(2, physical))
        reason = "latency/I-O sensitive stage prefers physical-core scale over SMT saturation"
    elif stage in {"color", "scale", "encode", "vfx_cpu", "neural_cpu"}:
        target = available
        reason = "CPU-heavy stage may use the measured machine envelope instead of the legacy 8-thread cap"
    else:
        target = min(available, max(2, physical))
        reason = "conservative generic stage budget"

    if gpu_active and stage in {"color", "scale", "encode", "vfx_cpu"} and logical >= 8:
        target = min(target, max(2, available - 1))
        reason += "; one extra logical processor is left for GPU driver/feed work"

    if thermal_constrained and logical >= 6:
        reduced = max(2, int(round(target * 0.75)))
        if reduced < target:
            target = reduced
            reason += "; reduced 25% because sustained telemetry indicates thermal/power pressure"

    target = max(1, min(target, logical))
    return CpuSchedule(
        stage=stage,
        mode=mode,
        threads=target,
        logical_cpus=logical,
        physical_cores=physical,
        reserve_logical=max(0, logical - target),
        reason=reason,
    )


def candidate_thread_counts(
    stage: StageKind,
    *,
    topology: CpuTopology | None = None,
    mode: MachineMode = "balanced",
    gpu_active: bool = False,
) -> tuple[int, ...]:
    """Return bounded benchmark candidates around the scheduler recommendation.

    H1 intentionally benchmarks a small monotonic set instead of blindly forcing
    every thread. Candidate selection is quality-neutral: only concurrency changes.
    """
    schedule = schedule_cpu_threads(stage, topology=topology, mode=mode, gpu_active=gpu_active)
    topology = topology or CpuTopology(schedule.logical_cpus, schedule.physical_cores)
    candidates = {
        max(1, topology.physical_cores),
        max(1, schedule.threads),
        max(1, int(round(schedule.threads * 0.75))),
    }
    return tuple(sorted(value for value in candidates if value <= topology.logical_cpus))


def choose_proven_thread_count(
    samples: Iterable[tuple[int, float, bool]],
    *,
    fallback_threads: int,
) -> int:
    """Choose fastest verified candidate; invalid/integrity-failed samples never win.

    Samples are ``(threads, wall_seconds, integrity_ok)``. This keeps H1's policy
    subordinate to image/temporal/color/audio/recovery gates instead of treating
    throughput as the only metric.
    """
    valid = [item for item in samples if item[0] > 0 and item[1] > 0 and item[2]]
    if not valid:
        return max(1, int(fallback_threads))
    return min(valid, key=lambda item: item[1])[0]
