from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


Stage = Literal["realesrgan", "rife"]


@dataclass(frozen=True)
class PipelineBudget:
    stage: Stage
    chunk_budget_gb: float
    max_inflight_chunks: int
    overlap_extract: bool
    overlap_pack: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def derive_pipeline_budget(
    stage: Stage,
    *,
    ram_available_gb: float | None,
    vram_free_mb: float | None,
    scratch_free_gb: float,
    scratch_write_mbps: float | None,
    dedicated: bool = False,
) -> PipelineBudget:
    """Derive a bounded neural chunk/overlap budget from live resource headroom.

    This function changes only buffering and overlap. It never changes model,
    scale, interpolation cadence, color/HDR transforms or encoder quality.
    Unknown telemetry fails toward the historical 4 GiB-or-smaller envelope.
    """
    if stage not in {"realesrgan", "rife"}:
        raise ValueError(f"unsupported pipeline stage: {stage}")
    ram = max(0.0, float(ram_available_gb or 0.0))
    vram_gb = max(0.0, float(vram_free_mb or 0.0)) / 1024.0
    scratch = max(0.0, float(scratch_free_gb))
    speed = None if scratch_write_mbps is None else max(0.0, float(scratch_write_mbps))

    # Preserve OS/driver/UI headroom even in Dedicated mode. The neural PNG
    # workset is disk-backed, so RAM is a guardrail rather than a target.
    ram_reserve = max(2.0, ram * (0.15 if dedicated else 0.25))
    ram_usable = max(0.25, ram - ram_reserve) if ram > 0 else 4.0
    scratch_reserve = max(2.0, scratch * 0.10)
    scratch_usable = max(0.25, scratch - scratch_reserve)

    # RIFE can materialize roughly 2x+ output frames for one input chunk, so
    # keep a tighter default than Real-ESRGAN at the same machine headroom.
    stage_cap = 8.0 if stage == "realesrgan" else 6.0
    base = min(stage_cap, ram_usable * 0.30, scratch_usable * 0.20)
    if vram_gb > 0:
        base = min(base, max(1.0, vram_gb * (0.75 if stage == "realesrgan" else 0.55)))
    # Never expand solely because one critical resource signal is absent.
    # Legacy 4 GiB remains the upper fallback until RAM, scratch and VRAM
    # headroom are all known. Throughput controls overlap separately below.
    if ram <= 0 or scratch <= 0 or vram_gb <= 0:
        base = min(base, 4.0)
    chunk_budget = max(0.5, min(stage_cap, base))

    fast_scratch = speed is not None and speed >= 350.0
    healthy_ram = ram >= 8.0
    healthy_vram = vram_gb >= (4.0 if stage == "realesrgan" else 5.0)
    overlap_extract = bool(fast_scratch and healthy_ram)
    overlap_pack = bool(fast_scratch and healthy_ram and healthy_vram)
    max_inflight = 1
    if overlap_extract:
        max_inflight = 2
    if overlap_extract and overlap_pack and dedicated and ram >= 16.0 and scratch >= chunk_budget * 6.0:
        max_inflight = 3
    # Hard backpressure: H4 never allows an unbounded queue.
    max_inflight = max(1, min(3, max_inflight))

    reasons = [
        f"chunk={chunk_budget:.2f}GiB from RAM/scratch/VRAM headroom",
        f"scratch={'unknown' if speed is None else f'{speed:.0f}MB/s'}",
        f"inflight={max_inflight}",
    ]
    if not fast_scratch:
        reasons.append("overlap limited because scratch throughput is not proven fast")
    if not healthy_ram:
        reasons.append("overlap limited by RAM headroom")
    if not healthy_vram:
        reasons.append("pack overlap limited by VRAM headroom")
    return PipelineBudget(
        stage=stage,
        chunk_budget_gb=chunk_budget,
        max_inflight_chunks=max_inflight,
        overlap_extract=overlap_extract,
        overlap_pack=overlap_pack,
        reason="; ".join(reasons),
    )
