from __future__ import annotations

import ctypes
import os
import platform
import secrets
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .hardware_telemetry import NvidiaSmiSampler


MIB = 1024 ** 2
GIB = 1024 ** 3


@dataclass(frozen=True)
class ResourceHeadroom:
    ram_available_gb: float | None
    vram_free_mb: float | None
    scratch_free_gb: float
    scratch_write_mbps: float | None
    gpu_index: int
    probe_bytes: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def ram_available_gb() -> float | None:
    """Return currently available physical RAM using only OS interfaces."""
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(status)
        try:
            ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        except (AttributeError, OSError):
            return None
        return float(status.ullAvailPhys) / GIB if ok else None

    if platform.system() == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.startswith("MemAvailable:"):
                    continue
                value_kib = float(line.split()[1])
                return value_kib * 1024.0 / GIB
        except (OSError, ValueError, IndexError):
            return None
    return None


def vram_free_mb(gpu_index: int = 0, *, sampler: NvidiaSmiSampler | None = None) -> float | None:
    """Return free VRAM for the selected NVIDIA adapter, when exposed."""
    selected = max(0, int(gpu_index))
    source = sampler if sampler is not None else NvidiaSmiSampler()
    try:
        samples = source.sample()
    except Exception:
        return None
    for gpu in samples:
        if int(gpu.index) == selected:
            return float(gpu.vram_free_mb) if gpu.vram_free_mb is not None else None
    return None


def measure_scratch_write_mbps(
    scratch: Path,
    *,
    size_mb: int = 32,
    minimum_free_gb: float = 1.0,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[float | None, int]:
    """Measure bounded synchronous sequential write throughput on the scratch volume.

    The probe is deliberately small, uses a non-sparse pseudo-random block,
    flushes it with fsync, and always removes its temporary file. If free-space
    headroom is too small or any filesystem operation fails, H4 fails closed by
    returning no throughput evidence.
    """
    root = Path(scratch)
    requested = max(1, min(128, int(size_mb))) * MIB
    try:
        root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(root)
    except OSError:
        return None, 0
    reserve = max(int(max(0.0, float(minimum_free_gb)) * GIB), requested * 4)
    if usage.free <= reserve:
        return None, 0

    block = secrets.token_bytes(MIB)
    path: Path | None = None
    started = clock()
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix="cinepulse-h4-write-",
            suffix=".probe",
            dir=root,
            delete=False,
        )
        path = Path(handle.name)
        try:
            remaining = requested
            while remaining > 0:
                current = block if remaining >= len(block) else block[:remaining]
                handle.write(current)
                remaining -= len(current)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        elapsed = max(0.000001, clock() - started)
        return requested / 1_000_000.0 / elapsed, requested
    except OSError:
        return None, 0
    finally:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def measure_resource_headroom(
    scratch: Path,
    *,
    gpu_index: int = 0,
    probe_write: bool = True,
    probe_size_mb: int = 32,
) -> ResourceHeadroom:
    """Capture the bounded live evidence used by H4 neural chunk planning."""
    root = Path(scratch)
    try:
        free_gb = shutil.disk_usage(root).free / GIB
    except OSError:
        free_gb = 0.0
    write_mbps: float | None = None
    probe_bytes = 0
    if probe_write:
        write_mbps, probe_bytes = measure_scratch_write_mbps(root, size_mb=probe_size_mb)
    return ResourceHeadroom(
        ram_available_gb=ram_available_gb(),
        vram_free_mb=vram_free_mb(gpu_index),
        scratch_free_gb=max(0.0, float(free_gb)),
        scratch_write_mbps=write_mbps,
        gpu_index=max(0, int(gpu_index)),
        probe_bytes=probe_bytes,
    )
