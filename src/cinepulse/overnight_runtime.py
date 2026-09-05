from __future__ import annotations

"""Sustained, quality-neutral overnight scheduling for Hardware MegaPack H8.

The controller observes telemetry only and returns bounded scheduling hints. It
never changes quality settings, clocks, fan curves, process priority classes,
system power plans, models, target FPS, color/HDR or recovery behavior.

Its purpose is end-to-end throughput: reduce upstream pressure when heat, shared
power or scratch saturation would otherwise make a long render slower or less
stable. It never tries to force every component to 100% utilization.
"""

from collections import deque
from dataclasses import asdict, dataclass
from statistics import mean

from .hardware_telemetry import HardwareSample


@dataclass(frozen=True)
class OvernightDecision:
    pressure_level: int
    cpu_scale: float
    chunk_scale: float
    overlap_depth: int
    cooldown_hint_seconds: float
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def limit_threads(self, baseline: int, *, minimum: int = 1) -> int:
        base = max(minimum, int(baseline))
        return max(minimum, min(base, round(base * self.cpu_scale)))

    def limit_chunk_frames(self, baseline: int, *, minimum: int = 1) -> int:
        base = max(minimum, int(baseline))
        return max(minimum, min(base, round(base * self.chunk_scale)))


class OvernightRuntimeController:
    """Windowed downshift controller for unattended sustained renders.

    Decisions are monotonic inside a render. This avoids saw-tooth oscillation
    between hot/aggressive and cool/conservative policies. A fresh render starts
    from its benchmark-proven baseline again.
    """

    def __init__(
        self,
        *,
        gpu_index: int = 0,
        scratch_sustainable_mbps: float | None = None,
        window: int = 4,
        baseline_overlap_depth: int = 3,
    ) -> None:
        self.gpu_index = max(0, int(gpu_index))
        self.scratch_sustainable_mbps = (
            max(1.0, float(scratch_sustainable_mbps)) if scratch_sustainable_mbps is not None else None
        )
        self.window = max(2, min(12, int(window)))
        self.baseline_overlap_depth = max(1, min(3, int(baseline_overlap_depth)))
        self._samples: deque[HardwareSample] = deque(maxlen=self.window)
        self._level = 0
        self._reasons: tuple[str, ...] = ()

    @property
    def pressure_level(self) -> int:
        return self._level

    def _decision(self) -> OvernightDecision:
        if self._level >= 3:
            return OvernightDecision(3, 0.60, 0.50, 1, 10.0, self._reasons)
        if self._level == 2:
            return OvernightDecision(2, 0.75, 0.65, 1, 2.0, self._reasons)
        if self._level == 1:
            return OvernightDecision(1, 0.88, 0.80, min(2, self.baseline_overlap_depth), 0.0, self._reasons)
        return OvernightDecision(0, 1.0, 1.0, self.baseline_overlap_depth, 0.0, self._reasons)

    def observe(self, sample: HardwareSample | None) -> OvernightDecision:
        if sample is None:
            return self._decision()
        self._samples.append(sample)
        if len(self._samples) < self.window:
            return self._decision()

        selected = []
        for item in self._samples:
            gpu = next((gpu for gpu in item.gpus if int(gpu.index) == self.gpu_index), None)
            if gpu is not None:
                selected.append(gpu)

        temperatures = [float(gpu.temperature_c) for gpu in selected if gpu.temperature_c is not None]
        gpu_utils = [float(gpu.utilization_percent) for gpu in selected if gpu.utilization_percent is not None]
        powers = [float(gpu.power_w) for gpu in selected if gpu.power_w is not None]
        power_limits = [float(gpu.power_limit_w) for gpu in selected if gpu.power_limit_w is not None and gpu.power_limit_w > 0]
        clocks = [float(gpu.graphics_clock_mhz) for gpu in selected if gpu.graphics_clock_mhz is not None]
        ram = [float(item.ram_percent) for item in self._samples if item.ram_percent is not None]
        disk = [
            max(0.0, float(item.disk_read_mbps or 0.0)) + max(0.0, float(item.disk_write_mbps or 0.0))
            for item in self._samples
        ]

        reasons: list[str] = []
        requested = 0
        avg_temp = mean(temperatures) if temperatures else None
        if avg_temp is not None:
            if avg_temp >= 88.0:
                requested = max(requested, 3)
                reasons.append(f"temperatura GPU sustentada {avg_temp:.1f}°C")
            elif avg_temp >= 85.0:
                requested = max(requested, 2)
                reasons.append(f"temperatura GPU sustentada {avg_temp:.1f}°C")
            elif avg_temp >= 82.0:
                requested = max(requested, 1)
                reasons.append(f"temperatura GPU elevada {avg_temp:.1f}°C")

        avg_ram = mean(ram) if ram else None
        if avg_ram is not None:
            if avg_ram >= 94.0:
                requested = max(requested, 3)
                reasons.append(f"RAM sustentada {avg_ram:.1f}%")
            elif avg_ram >= 89.0:
                requested = max(requested, 2)
                reasons.append(f"RAM sustentada {avg_ram:.1f}%")

        avg_power = mean(powers) if powers else None
        avg_limit = mean(power_limits) if power_limits else None
        avg_gpu = mean(gpu_utils) if gpu_utils else None
        # Near-limit power while utilization is below saturation commonly means
        # shared laptop power/thermal pressure rather than a need for more work.
        if avg_power is not None and avg_limit is not None and avg_limit > 0:
            ratio = avg_power / avg_limit
            if ratio >= 0.96 and (avg_gpu is None or avg_gpu < 92.0):
                requested = max(requested, 2)
                reasons.append(f"GPU em {ratio * 100:.0f}% do limite de potência sem saturação útil")

        if len(clocks) >= 2 and max(clocks) > 0 and min(clocks) / max(clocks) < 0.72:
            requested = max(requested, 1)
            reasons.append("clock GPU caiu >28% dentro da janela sustentada")

        if self.scratch_sustainable_mbps is not None and disk:
            avg_disk = mean(disk)
            ratio = avg_disk / self.scratch_sustainable_mbps
            if ratio >= 0.92:
                requested = max(requested, 2)
                reasons.append(f"scratch sustentado em {ratio * 100:.0f}% da vazão medida")
            elif ratio >= 0.80:
                requested = max(requested, 1)
                reasons.append(f"scratch elevado em {ratio * 100:.0f}% da vazão medida")

        if requested > self._level:
            self._level = requested
            self._reasons = tuple(reasons)
        return self._decision()
