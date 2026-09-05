from __future__ import annotations

from dataclasses import asdict, dataclass

from .hardware_telemetry import HardwareSample


@dataclass(frozen=True)
class RuntimePressureDecision:
    """Quality-neutral scheduling envelope for the remainder of one render.

    H5 is intentionally downshift-only.  A live sample may reduce future chunk
    size and disable H4 overlap, but it can never increase concurrency beyond
    the H4 policy selected before the render began.
    """

    level: int
    chunk_scale: float
    allow_extract_overlap: bool
    allow_pack_overlap: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def limit_chunk_frames(self, baseline: int, *, minimum: int = 1) -> int:
        base = max(int(minimum), int(baseline))
        return max(int(minimum), min(base, int(round(base * self.chunk_scale))))


class AdaptiveRuntimeController:
    """Monotonic per-render pressure controller.

    The controller never changes models, scale, target FPS, color/HDR,
    interpolation, codec quality or verification.  It only reduces future H4
    buffering/concurrency when sustained-machine evidence reaches conservative
    pressure thresholds.  Once reduced, the render never automatically ramps
    back up, avoiding thermal/memory oscillation and unproven performance tuning.
    """

    def __init__(
        self,
        *,
        gpu_index: int = 0,
        allow_extract_overlap: bool = False,
        allow_pack_overlap: bool = False,
    ) -> None:
        self.gpu_index = max(0, int(gpu_index))
        self._baseline_extract = bool(allow_extract_overlap)
        self._baseline_pack = bool(allow_pack_overlap)
        self._level = 0
        self._reasons: tuple[str, ...] = ()

    @property
    def level(self) -> int:
        return self._level

    def _decision(self) -> RuntimePressureDecision:
        if self._level >= 2:
            return RuntimePressureDecision(2, 0.50, False, False, self._reasons)
        if self._level == 1:
            return RuntimePressureDecision(1, 0.75, False, False, self._reasons)
        return RuntimePressureDecision(
            0,
            1.0,
            self._baseline_extract,
            self._baseline_pack,
            self._reasons,
        )

    def observe(self, sample: HardwareSample | None) -> RuntimePressureDecision:
        if sample is None:
            return self._decision()

        selected_gpu = next((gpu for gpu in sample.gpus if int(gpu.index) == self.gpu_index), None)
        temperature = selected_gpu.temperature_c if selected_gpu is not None else None
        vram_free = selected_gpu.vram_free_mb if selected_gpu is not None else None
        ram_percent = sample.ram_percent

        critical: list[str] = []
        caution: list[str] = []

        if temperature is not None:
            if temperature >= 88.0:
                critical.append(f"GPU {temperature:.1f}°C")
            elif temperature >= 84.0:
                caution.append(f"GPU {temperature:.1f}°C")
        if ram_percent is not None:
            if ram_percent >= 94.0:
                critical.append(f"RAM {ram_percent:.1f}%")
            elif ram_percent >= 88.0:
                caution.append(f"RAM {ram_percent:.1f}%")
        if vram_free is not None:
            if vram_free < 384.0:
                critical.append(f"VRAM livre {vram_free:.0f} MB")
            elif vram_free < 768.0:
                caution.append(f"VRAM livre {vram_free:.0f} MB")

        requested = 2 if critical else (1 if caution else 0)
        if requested > self._level:
            self._level = requested
            evidence = critical if requested == 2 else caution
            self._reasons = tuple(evidence)
        return self._decision()
