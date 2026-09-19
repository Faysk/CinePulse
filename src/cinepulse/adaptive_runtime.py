from __future__ import annotations

from dataclasses import asdict, dataclass

from .hardware_telemetry import HardwareSample
from .overnight_runtime import OvernightRuntimeController


@dataclass(frozen=True)
class RuntimePressureDecision:
    """Quality-neutral scheduling envelope for the remainder of one render.

    CinePulse 1.2.4 keeps this object for API/history compatibility, but live
    telemetry no longer reduces chunk size, CPU threads or overlap. The render
    stays at its full-utilization baseline until a concrete operation fails.
    """

    level: int
    chunk_scale: float
    allow_extract_overlap: bool
    allow_pack_overlap: bool
    reasons: tuple[str, ...]
    cpu_scale: float = 1.0
    cooldown_hint_seconds: float = 0.0

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def limit_chunk_frames(self, baseline: int, *, minimum: int = 1) -> int:
        base = max(int(minimum), int(baseline))
        return max(int(minimum), min(base, int(round(base * self.chunk_scale))))

    def limit_cpu_threads(self, baseline: int, *, minimum: int = 1) -> int:
        base = max(int(minimum), int(baseline))
        return max(int(minimum), min(base, int(round(base * self.cpu_scale))))


class AdaptiveRuntimeController:
    """Hysteretic per-render pressure controller.

    The controller never changes models, scale, target FPS, color/HDR,
    interpolation, codec quality or verification. It only reduces future
    buffering/concurrency for capacity/stability pressure. Temperature alone is
    observational: H8 thermal/power/clock downshift requires a sustained decline
    in measured completed-work throughput.

    ``overnight=True`` adds H8's sustained window and learned neural-throughput
    warm-up on top of the RAM/VRAM capacity guard. Capacity-only downshifts may
    recover one level after several deeply healthy samples, but never above the
    policy the render started with. Overnight instability/thermal decisions stay
    monotonic because the H8 controller itself remains monotonic.
    """

    def __init__(
        self,
        *,
        gpu_index: int = 0,
        allow_extract_overlap: bool = False,
        allow_pack_overlap: bool = False,
        overnight: bool = False,
        scratch_sustainable_mbps: float | None = None,
        overnight_window: int = 4,
        recovery_window: int = 4,
    ) -> None:
        self.gpu_index = max(0, int(gpu_index))
        self._baseline_extract = bool(allow_extract_overlap)
        self._baseline_pack = bool(allow_pack_overlap)
        self._level = 0
        self._reasons: tuple[str, ...] = ()
        self._cpu_scale = 1.0
        self._cooldown_hint_seconds = 0.0
        self._recovery_window = max(3, min(12, int(recovery_window)))
        self._healthy_streak = 0
        overlap_depth = 3 if self._baseline_extract and self._baseline_pack else (
            2 if self._baseline_extract or self._baseline_pack else 1
        )
        self._overnight = OvernightRuntimeController(
            gpu_index=self.gpu_index,
            scratch_sustainable_mbps=scratch_sustainable_mbps,
            window=overnight_window,
            baseline_overlap_depth=overlap_depth,
        ) if overnight else None

    @property
    def level(self) -> int:
        return self._level

    @property
    def throughput_ratio(self) -> float | None:
        return self._overnight.throughput_ratio if self._overnight is not None else None

    def record_throughput(self, units_per_second: float) -> None:
        if self._overnight is not None:
            self._overnight.record_throughput(units_per_second)

    def record_instability(self) -> None:
        if self._overnight is not None:
            self._overnight.record_instability()

    def _decision(self) -> RuntimePressureDecision:
        if self._level >= 2:
            return RuntimePressureDecision(
                2, 0.50, False, False, self._reasons,
                cpu_scale=min(1.0, self._cpu_scale),
                cooldown_hint_seconds=self._cooldown_hint_seconds,
            )
        if self._level == 1:
            return RuntimePressureDecision(
                1, 0.75, False, False, self._reasons,
                cpu_scale=min(1.0, self._cpu_scale),
                cooldown_hint_seconds=self._cooldown_hint_seconds,
            )
        return RuntimePressureDecision(
            0,
            1.0,
            self._baseline_extract,
            self._baseline_pack,
            self._reasons,
            cpu_scale=min(1.0, self._cpu_scale),
            cooldown_hint_seconds=self._cooldown_hint_seconds,
        )

    def observe(self, sample: HardwareSample | None) -> RuntimePressureDecision:
        """Keep the baseline envelope regardless of live resource telemetry."""
        del sample
        self._level = 0
        self._reasons = ()
        self._cpu_scale = 1.0
        self._cooldown_hint_seconds = 0.0
        self._healthy_streak = 0
        return self._decision()
