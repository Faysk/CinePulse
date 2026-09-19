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

    # Preserve OS/driver/UI headroom even in Dedicated mode, but let abundant
    # host RAM become a real throughput resource. Neural tools still use file
    # paths, so the OS page cache is the zero-copy-compatible RAM cache: larger
    # bounded chunks reduce process/FFmpeg churn and keep recently written PNGs
    # hot in memory for the next stage instead of forcing tiny disk-backed lots.
    ram_reserve = max(4.0 if dedicated else 6.0, ram * (0.12 if dedicated else 0.20))
    ram_usable = max(0.25, ram - ram_reserve) if ram > 0 else 4.0
    scratch_reserve = max(2.0, scratch * 0.10)
    scratch_usable = max(0.25, scratch - scratch_reserve)

    # Chunk length primarily consumes host RAM/page-cache + scratch. VRAM is
    # governed independently by model tile/process concurrency, so tying chunk
    # length linearly to free VRAM unnecessarily starved high-RAM / 8 GB systems.
    # RIFE remains tighter because it can materialize 2x+ output frames.
    stage_cap = 16.0 if stage == "realesrgan" else 12.0
    ram_fraction = 0.40 if stage == "realesrgan" else 0.32
    base = min(stage_cap, ram_usable * ram_fraction, scratch_usable * 0.20)

    # Never expand solely because one critical signal is absent. Legacy 4 GiB
    # remains the upper fallback until RAM, scratch and VRAM telemetry are all
    # known, even though VRAM no longer directly caps the host workset.
    if ram <= 0 or scratch <= 0 or vram_gb <= 0:
        base = min(base, 4.0)
    chunk_budget = max(0.5, min(stage_cap, base))

    fast_scratch = speed is not None and speed >= 350.0
    healthy_ram = ram >= 8.0
    healthy_vram = vram_gb >= (4.0 if stage == "realesrgan" else 5.0)
    overlap_extract = bool(fast_scratch and healthy_ram)
    # Studio overlaps a background pack only for Real-ESRGAN. RIFE has current
    # + one prefetched input chunk, so budgeting a third workset there would
    # shrink chunks for concurrency that never actually exists.
    overlap_pack = bool(
        stage == "realesrgan" and fast_scratch and healthy_ram and healthy_vram
    )
    max_inflight = 1
    if overlap_extract:
        max_inflight = 2
    if overlap_extract and overlap_pack and dedicated and ram >= 16.0 and scratch >= chunk_budget * 6.0:
        max_inflight = 3

    # Make the per-workset budget concurrency-aware. Three individually safe
    # chunks must not collectively consume nearly all currently available RAM.
    # This still lets large-memory machines grow beyond the legacy 4 GiB chunk,
    # while reserving capacity for the OS, driver, encoder and filesystem.
    ram_share = 0.72 if dedicated else 0.60
    concurrent_ram_cap = max(0.5, ram_usable * ram_share / max(1, max_inflight))
    chunk_budget = min(chunk_budget, concurrent_ram_cap)

    # A smaller concurrency-aware chunk may make a third bounded workset safe
    # on scratch. Re-evaluate once, then recompute the host-memory cap.
    if (
        max_inflight < 3
        and overlap_extract
        and overlap_pack
        and dedicated
        and ram >= 16.0
        and scratch >= chunk_budget * 6.0
    ):
        max_inflight = 3
        concurrent_ram_cap = max(0.5, ram_usable * ram_share / max_inflight)
        chunk_budget = min(chunk_budget, concurrent_ram_cap)

    # The runtime represents extract/pack overlap as independent booleans.
    # Allowing both while claiming inflight=2 would actually materialize the
    # current neural chunk + one prefetched chunk + one background pack = 3.
    # Keep the advertised hard bound truthful.
    if max_inflight < 3 and overlap_extract and overlap_pack:
        overlap_pack = False

    # Hard backpressure: H4 never allows an unbounded queue.
    max_inflight = max(1, min(3, max_inflight))

    reasons = [
        f"chunk={chunk_budget:.2f}GiB host workset from RAM/page-cache + scratch headroom (inflight-aware)",
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
