from __future__ import annotations

"""Derive H0 throughput from real render-stage events and measured wall time.

No target FPS or predicted workload is used here.  A throughput record exists
only when a stage event itself contains an explicit completed/planned frame
count emitted by the runtime.  This keeps benchmark evidence honest and avoids
turning a requested 120 fps target into a fake measured 120 frames/s result.
"""

from dataclasses import dataclass, asdict
import re
from typing import Any, Iterable, Mapping


_FRAME_PATTERNS = (
    # Neural processing events emitted once per chunk.
    re.compile(r"\bReal-ESRGAN\s+em\s+(\d+)\s+quadro", re.IGNORECASE),
    re.compile(r"\bgerando\s+(\d+)\s+quadro", re.IGNORECASE),
    # Extract stages are separate stage names, so their real decoded frame rate
    # is useful independently and is not double-counted into the neural stage.
    re.compile(r"\bextraindo\s+(\d+)\s+quadro", re.IGNORECASE),
    # A few packing/status messages use this simpler form.
    re.compile(r"\b(\d+)\s+quadro\(s\)", re.IGNORECASE),
)


@dataclass(frozen=True)
class StageThroughput:
    stage: str
    work_units: int
    work_unit: str
    wall_seconds: float
    units_per_second: float
    evidence_events: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _frames_from_detail(detail: str) -> int | None:
    text = str(detail or "")
    for pattern in _FRAME_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                return None
            return value if value > 0 else None
    return None


def derive_stage_throughput(
    stage_events: Iterable[Mapping[str, Any]],
    stage_summary: Mapping[str, Any],
) -> dict[str, dict[str, object]]:
    """Return measured frame throughput only for stages with explicit work.

    Multiple chunk events for the same stage are summed.  Stages without an
    explicit runtime frame count are omitted rather than assigned an estimate.
    """
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    for event in stage_events:
        stage = str(event.get("stage") or "").strip()
        if not stage:
            continue
        frames = _frames_from_detail(str(event.get("detail") or ""))
        if frames is None:
            continue
        totals[stage] = totals.get(stage, 0) + frames
        counts[stage] = counts.get(stage, 0) + 1

    result: dict[str, dict[str, object]] = {}
    for stage, units in sorted(totals.items()):
        summary = stage_summary.get(stage)
        if not isinstance(summary, Mapping):
            continue
        try:
            wall = float(summary.get("wall_seconds") or 0.0)
        except (TypeError, ValueError):
            continue
        if wall <= 0:
            continue
        record = StageThroughput(
            stage=stage,
            work_units=units,
            work_unit="frames",
            wall_seconds=wall,
            units_per_second=units / wall,
            evidence_events=counts.get(stage, 0),
        )
        result[stage] = record.to_dict()
    return result


def throughput_from_telemetry(payload: Mapping[str, Any]) -> dict[str, object]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    stages = summary.get("stages") if isinstance(summary.get("stages"), Mapping) else {}
    events = payload.get("stage_events") if isinstance(payload.get("stage_events"), list) else []
    measured = derive_stage_throughput(events, stages)
    return {
        "schema": 1,
        "source": "runtime-stage-events-plus-measured-wall-time",
        "estimated": False,
        "stages": measured,
    }
