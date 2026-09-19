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
    """Return the fixed full-utilization neural pipeline envelope.

    RAM/VRAM headroom, scratch throughput and profile reservations are not used
    to throttle work in 1.2.4. The only remaining bounds are structural ones
    required by the implementation: Real-ESRGAN supports current + prefetch +
    background pack (3 worksets), while RIFE supports current + prefetch (2).

    Capacity/integrity checks elsewhere may still reject an impossible output;
    this function no longer reduces utilization pre-emptively.
    """
    del ram_available_gb, vram_free_mb, scratch_free_gb, scratch_write_mbps, dedicated
    if stage not in {"realesrgan", "rife"}:
        raise ValueError(f"unsupported pipeline stage: {stage}")

    if stage == "realesrgan":
        return PipelineBudget(
            stage=stage,
            chunk_budget_gb=16.0,
            max_inflight_chunks=3,
            overlap_extract=True,
            overlap_pack=True,
            reason="full-utilization fixed envelope: 16GiB workset; extract+pack overlap; inflight=3",
        )

    return PipelineBudget(
        stage=stage,
        chunk_budget_gb=12.0,
        max_inflight_chunks=2,
        overlap_extract=True,
        overlap_pack=False,
        reason="full-utilization fixed envelope: 12GiB workset; extract overlap; inflight=2",
    )
