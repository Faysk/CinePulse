from __future__ import annotations

import csv
import ctypes
import json
import math
import os
import platform
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
TELEMETRY_SCHEMA = 1
DEFAULT_INTERVAL_SECONDS = 2.0


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    return value if math.isfinite(value) else None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "na", "[not supported]", "not supported"}:
        return None
    try:
        return _finite(float(text))
    except ValueError:
        return None


def _mean(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return sum(valid) / len(valid) if valid else None


def _maximum(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return max(valid) if valid else None


def _minimum(values: Iterable[float | None]) -> float | None:
    valid = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return min(valid) if valid else None


@dataclass(frozen=True)
class GpuSample:
    index: int
    name: str
    driver: str | None = None
    utilization_percent: float | None = None
    memory_utilization_percent: float | None = None
    vram_total_mb: float | None = None
    vram_used_mb: float | None = None
    vram_free_mb: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    temperature_c: float | None = None
    graphics_clock_mhz: float | None = None
    memory_clock_mhz: float | None = None
    pstate: str | None = None


@dataclass(frozen=True)
class HardwareSample:
    timestamp: float
    monotonic: float
    stage: str
    cpu_total_percent: float | None
    cpu_per_logical_percent: tuple[float, ...]
    ram_total_mb: float | None
    ram_used_mb: float | None
    ram_available_mb: float | None
    ram_percent: float | None
    disk_read_mbps: float | None
    disk_write_mbps: float | None
    gpus: tuple[GpuSample, ...]


@dataclass(frozen=True)
class StageEvent:
    timestamp: float
    monotonic: float
    stage: str
    detail: str


@dataclass
class TelemetryPayload:
    schema: int
    started_at: float
    finished_at: float | None
    status: str
    sample_interval_seconds: float
    platform: str
    hostname: str
    cpu_threads: int
    source: str
    capabilities: dict[str, Any]
    stage_events: list[dict[str, Any]] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class _CpuSampler:
    def sample(self) -> tuple[float | None, tuple[float, ...]]:
        return None, ()


class _LinuxCpuSampler(_CpuSampler):
    def __init__(self) -> None:
        self._previous: dict[str, tuple[int, int]] | None = None

    @staticmethod
    def _read() -> dict[str, tuple[int, int]]:
        result: dict[str, tuple[int, int]] = {}
        try:
            lines = Path("/proc/stat").read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return result
        for line in lines:
            parts = line.split()
            if not parts or not parts[0].startswith("cpu"):
                continue
            if parts[0] != "cpu" and not parts[0][3:].isdigit():
                continue
            try:
                values = [int(value) for value in parts[1:]]
            except ValueError:
                continue
            idle = (values[3] if len(values) > 3 else 0) + (values[4] if len(values) > 4 else 0)
            total = sum(values)
            result[parts[0]] = (total, idle)
        return result

    def sample(self) -> tuple[float | None, tuple[float, ...]]:
        current = self._read()
        previous = self._previous
        self._previous = current
        if not previous:
            return None, ()

        def usage(key: str) -> float | None:
            if key not in current or key not in previous:
                return None
            total_delta = current[key][0] - previous[key][0]
            idle_delta = current[key][1] - previous[key][1]
            if total_delta <= 0:
                return None
            return max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0))

        logical_keys = sorted((key for key in current if key != "cpu"), key=lambda key: int(key[3:]))
        per_cpu = tuple(value for key in logical_keys if (value := usage(key)) is not None)
        return usage("cpu"), per_cpu


if os.name == "nt":
    class _SystemProcessorPerformanceInformation(ctypes.Structure):
        _fields_ = [
            ("IdleTime", ctypes.c_longlong),
            ("KernelTime", ctypes.c_longlong),
            ("UserTime", ctypes.c_longlong),
            ("DpcTime", ctypes.c_longlong),
            ("InterruptTime", ctypes.c_longlong),
            ("InterruptCount", ctypes.c_ulong),
        ]


class _WindowsCpuSampler(_CpuSampler):
    SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION = 8

    def __init__(self) -> None:
        self._previous: tuple[tuple[int, int], ...] | None = None
        self._ntdll = ctypes.WinDLL("ntdll") if os.name == "nt" else None

    def _read(self) -> tuple[tuple[int, int], ...]:
        if self._ntdll is None:
            return ()
        count = max(1, os.cpu_count() or 1)
        array_type = _SystemProcessorPerformanceInformation * count
        buffer = array_type()
        returned = ctypes.c_ulong(0)
        status = self._ntdll.NtQuerySystemInformation(
            self.SYSTEM_PROCESSOR_PERFORMANCE_INFORMATION,
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
            ctypes.byref(returned),
        )
        if status != 0:
            return ()
        item_size = ctypes.sizeof(_SystemProcessorPerformanceInformation)
        actual = min(count, returned.value // item_size if returned.value else count)
        return tuple((int(buffer[index].KernelTime + buffer[index].UserTime), int(buffer[index].IdleTime)) for index in range(actual))

    def sample(self) -> tuple[float | None, tuple[float, ...]]:
        current = self._read()
        previous = self._previous
        self._previous = current
        if not previous or len(previous) != len(current):
            return None, ()
        per_cpu: list[float] = []
        total_delta = 0
        idle_delta = 0
        for (total_now, idle_now), (total_before, idle_before) in zip(current, previous):
            delta_total = total_now - total_before
            delta_idle = idle_now - idle_before
            if delta_total <= 0:
                continue
            total_delta += delta_total
            idle_delta += max(0, delta_idle)
            per_cpu.append(max(0.0, min(100.0, (1.0 - max(0, delta_idle) / delta_total) * 100.0)))
        total = None if total_delta <= 0 else max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0))
        return total, tuple(per_cpu)


class _RamSampler:
    def sample(self) -> tuple[float | None, float | None, float | None, float | None]:
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
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                total = status.ullTotalPhys / 1024**2
                available = status.ullAvailPhys / 1024**2
                used = max(0.0, total - available)
                return total, used, available, float(status.dwMemoryLoad)
            return None, None, None, None

        if platform.system() == "Linux":
            values: dict[str, float] = {}
            try:
                for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
                    key, _, remainder = line.partition(":")
                    parts = remainder.strip().split()
                    if parts:
                        values[key] = float(parts[0]) / 1024.0
            except (OSError, ValueError):
                return None, None, None, None
            total = values.get("MemTotal")
            available = values.get("MemAvailable")
            if total is None or available is None:
                return total, None, available, None
            used = max(0.0, total - available)
            return total, used, available, (used / total * 100.0 if total else None)
        return None, None, None, None


class _DiskSampler:
    def sample(self, now: float) -> tuple[float | None, float | None]:
        return None, None

    def close(self) -> None:
        return None


class _LinuxDiskSampler(_DiskSampler):
    def __init__(self) -> None:
        self._previous: tuple[float, int, int] | None = None

    @staticmethod
    def _read_bytes() -> tuple[int, int]:
        read_bytes = 0
        write_bytes = 0
        root = Path("/sys/block")
        if not root.is_dir():
            return 0, 0
        for device in root.iterdir():
            try:
                fields = (device / "stat").read_text(encoding="ascii", errors="replace").split()
                sector_size_path = device / "queue" / "hw_sector_size"
                sector_size = int(sector_size_path.read_text(encoding="ascii").strip()) if sector_size_path.is_file() else 512
                if len(fields) >= 7:
                    read_bytes += int(fields[2]) * sector_size
                    write_bytes += int(fields[6]) * sector_size
            except (OSError, ValueError):
                continue
        return read_bytes, write_bytes

    def sample(self, now: float) -> tuple[float | None, float | None]:
        read_bytes, write_bytes = self._read_bytes()
        previous = self._previous
        self._previous = (now, read_bytes, write_bytes)
        if previous is None:
            return None, None
        elapsed = now - previous[0]
        if elapsed <= 0:
            return None, None
        read_mbps = max(0.0, read_bytes - previous[1]) / elapsed / 1_000_000
        write_mbps = max(0.0, write_bytes - previous[2]) / elapsed / 1_000_000
        return read_mbps, write_mbps


if os.name == "nt":
    class _PdhFmtUnion(ctypes.Union):
        _fields_ = [
            ("longValue", ctypes.c_long),
            ("doubleValue", ctypes.c_double),
            ("largeValue", ctypes.c_longlong),
            ("AnsiStringValue", ctypes.c_char_p),
            ("WideStringValue", ctypes.c_wchar_p),
        ]


    class _PdhFmtCounterValue(ctypes.Structure):
        _anonymous_ = ("value",)
        _fields_ = [("CStatus", ctypes.c_ulong), ("value", _PdhFmtUnion)]


class _WindowsDiskSampler(_DiskSampler):
    PDH_FMT_DOUBLE = 0x00000200

    def __init__(self) -> None:
        self._pdh = ctypes.WinDLL("pdh") if os.name == "nt" else None
        self._query = ctypes.c_void_p()
        self._read = ctypes.c_void_p()
        self._write = ctypes.c_void_p()
        self._ready = False
        if self._pdh is None:
            return
        if self._pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)) != 0:
            return
        add_counter = getattr(self._pdh, "PdhAddEnglishCounterW", self._pdh.PdhAddCounterW)
        if add_counter(self._query, r"\PhysicalDisk(_Total)\Disk Read Bytes/sec", 0, ctypes.byref(self._read)) != 0:
            self.close()
            return
        if add_counter(self._query, r"\PhysicalDisk(_Total)\Disk Write Bytes/sec", 0, ctypes.byref(self._write)) != 0:
            self.close()
            return
        if self._pdh.PdhCollectQueryData(self._query) != 0:
            self.close()
            return
        self._ready = True

    def _value(self, counter: ctypes.c_void_p) -> float | None:
        if not self._ready or self._pdh is None:
            return None
        value = _PdhFmtCounterValue()
        kind = ctypes.c_ulong(0)
        status = self._pdh.PdhGetFormattedCounterValue(counter, self.PDH_FMT_DOUBLE, ctypes.byref(kind), ctypes.byref(value))
        if status != 0 or value.CStatus != 0:
            return None
        return _finite(float(value.doubleValue))

    def sample(self, now: float) -> tuple[float | None, float | None]:
        del now
        if not self._ready or self._pdh is None:
            return None, None
        if self._pdh.PdhCollectQueryData(self._query) != 0:
            return None, None
        read = self._value(self._read)
        write = self._value(self._write)
        return (read / 1_000_000 if read is not None else None, write / 1_000_000 if write is not None else None)

    def close(self) -> None:
        if self._pdh is not None and self._query:
            try:
                self._pdh.PdhCloseQuery(self._query)
            except (AttributeError, OSError):
                pass
        self._query = ctypes.c_void_p()
        self._ready = False


class NvidiaSmiSampler:
    QUERY = (
        "index,name,driver_version,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,"
        "power.draw,power.limit,temperature.gpu,clocks.current.graphics,clocks.current.memory,pstate"
    )

    def __init__(self, executable: str | None = None, *, timeout: float = 1.5) -> None:
        self.executable = executable or shutil.which("nvidia-smi") or "nvidia-smi"
        self.timeout = max(0.25, float(timeout))

    def sample(self) -> tuple[GpuSample, ...]:
        try:
            result = subprocess.run(
                [self.executable, f"--query-gpu={self.QUERY}", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                creationflags=CREATE_NO_WINDOW,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ()
        if result.returncode != 0:
            return ()
        rows = csv.reader(line for line in result.stdout.splitlines() if line.strip())
        samples: list[GpuSample] = []
        for row in rows:
            if len(row) < 14:
                continue
            values = [item.strip() for item in row]
            try:
                index = int(values[0])
            except ValueError:
                continue
            samples.append(GpuSample(
                index=index,
                name=values[1],
                driver=values[2] or None,
                utilization_percent=_number(values[3]),
                memory_utilization_percent=_number(values[4]),
                vram_total_mb=_number(values[5]),
                vram_used_mb=_number(values[6]),
                vram_free_mb=_number(values[7]),
                power_w=_number(values[8]),
                power_limit_w=_number(values[9]),
                temperature_c=_number(values[10]),
                graphics_clock_mhz=_number(values[11]),
                memory_clock_mhz=_number(values[12]),
                pstate=values[13] or None,
            ))
        return tuple(samples)


def _make_cpu_sampler() -> _CpuSampler:
    if os.name == "nt":
        try:
            return _WindowsCpuSampler()
        except OSError:
            return _CpuSampler()
    if platform.system() == "Linux":
        return _LinuxCpuSampler()
    return _CpuSampler()


def _make_disk_sampler() -> _DiskSampler:
    if os.name == "nt":
        try:
            return _WindowsDiskSampler()
        except OSError:
            return _DiskSampler()
    if platform.system() == "Linux":
        return _LinuxDiskSampler()
    return _DiskSampler()


def telemetry_capabilities() -> dict[str, Any]:
    return {
        "gpu_nvidia_smi": bool(shutil.which("nvidia-smi")),
        "cpu_total": os.name == "nt" or platform.system() == "Linux",
        "cpu_per_logical": os.name == "nt" or platform.system() == "Linux",
        "memory": os.name == "nt" or platform.system() == "Linux",
        "disk_throughput": os.name == "nt" or platform.system() == "Linux",
        "power_temperature": bool(shutil.which("nvidia-smi")),
    }


def _sample_to_dict(sample: HardwareSample) -> dict[str, Any]:
    payload = asdict(sample)
    payload["cpu_per_logical_percent"] = list(sample.cpu_per_logical_percent)
    payload["gpus"] = [asdict(gpu) for gpu in sample.gpus]
    return payload


def _stage_durations(events: list[StageEvent], started: float, finished: float) -> dict[str, float]:
    if not events:
        return {"unclassified": max(0.0, finished - started)}
    durations: dict[str, float] = {}
    cursor_time = started
    cursor_stage = "startup"
    for event in sorted(events, key=lambda item: item.monotonic):
        durations[cursor_stage] = durations.get(cursor_stage, 0.0) + max(0.0, event.monotonic - cursor_time)
        cursor_stage = event.stage or "unclassified"
        cursor_time = event.monotonic
    durations[cursor_stage] = durations.get(cursor_stage, 0.0) + max(0.0, finished - cursor_time)
    return durations


def _active_gpu(samples: list[HardwareSample]) -> int | None:
    scores: dict[int, list[float]] = {}
    for sample in samples:
        for gpu in sample.gpus:
            if gpu.utilization_percent is not None:
                scores.setdefault(gpu.index, []).append(gpu.utilization_percent)
    if not scores:
        return None
    return max(scores, key=lambda index: _mean(scores[index]) or 0.0)


def summarize_samples(samples: list[HardwareSample], events: list[StageEvent], started: float, finished: float) -> dict[str, Any]:
    active_gpu_index = _active_gpu(samples)
    stage_durations = _stage_durations(events, started, finished)

    def summarize_group(group: list[HardwareSample], wall_seconds: float) -> dict[str, Any]:
        gpu_rows = [gpu for sample in group for gpu in sample.gpus if active_gpu_index is None or gpu.index == active_gpu_index]
        logical_count = max((len(sample.cpu_per_logical_percent) for sample in group), default=0)
        per_logical_peak = []
        for index in range(logical_count):
            per_logical_peak.append(_maximum(
                sample.cpu_per_logical_percent[index]
                for sample in group
                if index < len(sample.cpu_per_logical_percent)
            ))
        return {
            "wall_seconds": round(max(0.0, wall_seconds), 3),
            "sample_count": len(group),
            "cpu": {
                "average_percent": _mean(sample.cpu_total_percent for sample in group),
                "peak_percent": _maximum(sample.cpu_total_percent for sample in group),
                "per_logical_peak_percent": per_logical_peak,
            },
            "ram": {
                "peak_used_mb": _maximum(sample.ram_used_mb for sample in group),
                "minimum_available_mb": _minimum(sample.ram_available_mb for sample in group),
                "peak_percent": _maximum(sample.ram_percent for sample in group),
            },
            "disk": {
                "average_read_mbps": _mean(sample.disk_read_mbps for sample in group),
                "peak_read_mbps": _maximum(sample.disk_read_mbps for sample in group),
                "average_write_mbps": _mean(sample.disk_write_mbps for sample in group),
                "peak_write_mbps": _maximum(sample.disk_write_mbps for sample in group),
            },
            "gpu": {
                "index": active_gpu_index,
                "average_utilization_percent": _mean(gpu.utilization_percent for gpu in gpu_rows),
                "peak_utilization_percent": _maximum(gpu.utilization_percent for gpu in gpu_rows),
                "average_memory_utilization_percent": _mean(gpu.memory_utilization_percent for gpu in gpu_rows),
                "peak_vram_used_mb": _maximum(gpu.vram_used_mb for gpu in gpu_rows),
                "minimum_vram_free_mb": _minimum(gpu.vram_free_mb for gpu in gpu_rows),
                "average_power_w": _mean(gpu.power_w for gpu in gpu_rows),
                "peak_power_w": _maximum(gpu.power_w for gpu in gpu_rows),
                "peak_temperature_c": _maximum(gpu.temperature_c for gpu in gpu_rows),
                "average_graphics_clock_mhz": _mean(gpu.graphics_clock_mhz for gpu in gpu_rows),
                "average_memory_clock_mhz": _mean(gpu.memory_clock_mhz for gpu in gpu_rows),
            },
        }

    stages: dict[str, Any] = {}
    for stage, duration in stage_durations.items():
        group = [sample for sample in samples if sample.stage == stage]
        stages[stage] = summarize_group(group, duration)
    return {
        "wall_seconds": round(max(0.0, finished - started), 3),
        "active_gpu_index": active_gpu_index,
        "overall": summarize_group(samples, finished - started),
        "stages": stages,
    }


class HardwareTelemetrySession:
    """Low-overhead render telemetry recorder using only OS/vendor interfaces.

    Sampling is deliberately observational. It never changes clocks, priorities,
    power limits, fan curves, driver state or global OS policy.
    """

    def __init__(
        self,
        destination: Path,
        *,
        sample_interval: float = DEFAULT_INTERVAL_SECONDS,
        source: str = "render-history",
        gpu_sampler: Any | None = None,
        cpu_sampler: Any | None = None,
        ram_sampler: Any | None = None,
        disk_sampler: Any | None = None,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.destination = Path(destination)
        self.sample_interval = max(0.5, float(sample_interval))
        self.source = source
        self._gpu = gpu_sampler if gpu_sampler is not None else NvidiaSmiSampler()
        self._cpu = cpu_sampler if cpu_sampler is not None else _make_cpu_sampler()
        self._ram = ram_sampler if ram_sampler is not None else _RamSampler()
        self._disk = disk_sampler if disk_sampler is not None else _make_disk_sampler()
        self._clock = clock
        self._monotonic = monotonic
        self._started_wall = 0.0
        self._started_mono = 0.0
        self._stage = "startup"
        self._stage_detail = ""
        self._events: list[StageEvent] = []
        self._samples: list[HardwareSample] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "HardwareTelemetrySession":
        if self.running:
            return self
        self._started_wall = self._clock()
        self._started_mono = self._monotonic()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="cinepulse-hardware-telemetry", daemon=True)
        self._thread.start()
        return self

    def mark_stage(self, stage: str, detail: str = "") -> None:
        name = str(stage or "unclassified").strip() or "unclassified"
        with self._lock:
            self._stage = name
            self._stage_detail = str(detail or "")
            self._events.append(StageEvent(self._clock(), self._monotonic(), name, self._stage_detail))

    def _take_sample(self) -> HardwareSample:
        cpu_total, per_logical = self._cpu.sample()
        ram_total, ram_used, ram_available, ram_percent = self._ram.sample()
        now_mono = self._monotonic()
        disk_read, disk_write = self._disk.sample(now_mono)
        try:
            gpus = tuple(self._gpu.sample())
        except Exception:
            gpus = ()
        with self._lock:
            stage = self._stage
        return HardwareSample(
            timestamp=self._clock(),
            monotonic=now_mono,
            stage=stage,
            cpu_total_percent=_finite(cpu_total),
            cpu_per_logical_percent=tuple(_finite(value) or 0.0 for value in per_logical),
            ram_total_mb=_finite(ram_total),
            ram_used_mb=_finite(ram_used),
            ram_available_mb=_finite(ram_available),
            ram_percent=_finite(ram_percent),
            disk_read_mbps=_finite(disk_read),
            disk_write_mbps=_finite(disk_write),
            gpus=gpus,
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self._take_sample()
                with self._lock:
                    self._samples.append(sample)
            except Exception:
                pass
            self._stop.wait(self.sample_interval)

    def latest_sample(self) -> HardwareSample | None:
        """Return the newest observational sample without stopping telemetry."""
        with self._lock:
            return self._samples[-1] if self._samples else None

    def stop(self, *, status: str = "finished") -> dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(2.0, self.sample_interval * 2.5))
        finished_wall = self._clock()
        finished_mono = self._monotonic()
        with self._lock:
            samples = list(self._samples)
            events = list(self._events)
        summary = summarize_samples(samples, events, self._started_mono or finished_mono, finished_mono)
        payload = TelemetryPayload(
            schema=TELEMETRY_SCHEMA,
            started_at=self._started_wall or finished_wall,
            finished_at=finished_wall,
            status=str(status),
            sample_interval_seconds=self.sample_interval,
            platform=platform.platform(),
            hostname=platform.node(),
            cpu_threads=os.cpu_count() or 1,
            source=self.source,
            capabilities=telemetry_capabilities(),
            stage_events=[asdict(event) for event in events],
            samples=[_sample_to_dict(sample) for sample in samples],
            summary=summary,
        )
        document = asdict(payload)
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.destination.with_suffix(self.destination.suffix + ".tmp")
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.destination)
        try:
            self._disk.close()
        except Exception:
            pass
        self._thread = None
        return document


BENCHMARK_SCENARIOS: dict[str, dict[str, Any]] = {
    "720p24_to_8k120_music": {
        "label": "720p24 short clip -> 8K120 music project",
        "source": {"width": 1280, "height": 720, "fps": 24.0, "clip_seconds": 10.0},
        "target": {"width": 7680, "height": 4320, "fps": 120.0, "project_seconds": 264.0},
    },
    "1080p30_to_4k60": {
        "label": "1080p30 -> 4K60",
        "source": {"width": 1920, "height": 1080, "fps": 30.0},
        "target": {"width": 3840, "height": 2160, "fps": 60.0},
    },
}


def load_telemetry(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or int(payload.get("schema", 0)) != TELEMETRY_SCHEMA:
        raise ValueError("arquivo de telemetria CinePulse inválido ou incompatível")
    return payload


def benchmark_summary(payload: dict[str, Any], *, scenario: str | None = None) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    result = {
        "scenario": scenario,
        "scenario_contract": BENCHMARK_SCENARIOS.get(scenario) if scenario else None,
        "status": payload.get("status"),
        "wall_seconds": summary.get("wall_seconds"),
        "active_gpu_index": summary.get("active_gpu_index"),
        "overall": summary.get("overall", {}),
        "stages": summary.get("stages", {}),
    }
    return result


def compare_benchmarks(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_wall = _number(str(baseline.get("wall_seconds")))
    candidate_wall = _number(str(candidate.get("wall_seconds")))
    delta_seconds = None
    speedup = None
    improvement_percent = None
    if baseline_wall and candidate_wall and baseline_wall > 0 and candidate_wall > 0:
        delta_seconds = candidate_wall - baseline_wall
        speedup = baseline_wall / candidate_wall
        improvement_percent = (1.0 - candidate_wall / baseline_wall) * 100.0

    baseline_stages = baseline.get("stages") if isinstance(baseline.get("stages"), dict) else {}
    candidate_stages = candidate.get("stages") if isinstance(candidate.get("stages"), dict) else {}
    stage_comparison: dict[str, Any] = {}
    for stage in sorted(set(baseline_stages) | set(candidate_stages)):
        before = baseline_stages.get(stage, {})
        after = candidate_stages.get(stage, {})
        before_wall = _number(str(before.get("wall_seconds"))) if isinstance(before, dict) else None
        after_wall = _number(str(after.get("wall_seconds"))) if isinstance(after, dict) else None
        stage_speedup = before_wall / after_wall if before_wall and after_wall and after_wall > 0 else None
        stage_comparison[stage] = {
            "baseline_seconds": before_wall,
            "candidate_seconds": after_wall,
            "speedup": stage_speedup,
        }

    return {
        "baseline_seconds": baseline_wall,
        "candidate_seconds": candidate_wall,
        "delta_seconds": delta_seconds,
        "speedup": speedup,
        "improvement_percent": improvement_percent,
        "stages": stage_comparison,
    }
