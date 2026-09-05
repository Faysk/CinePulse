"""Preview-only restoration orchestration.

This module composes detector evidence, conservative overlay selection, optional
FFmpeg delogo fallback and bounded color restoration into one explicit plan.
It does not alter Stable render planning or delivery contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .restoration_color import RestorationColorControls, build_restoration_color_filter
from .restoration_detector import OverlaySamplingPolicy, inspect_video_for_overlays
from .restoration_overlay import (
    DetectionEvidence,
    OverlayRegion,
    build_overlay_removal_filtergraph,
    select_overlay_candidates,
)


@dataclass(frozen=True)
class PreviewRestorationPolicy:
    minimum_overlay_score: float = 0.62
    max_overlay_regions: int = 8
    overlay_iou_threshold: float = 0.45
    delogo_padding: int = 6

    def __post_init__(self) -> None:
        if not 0.0 <= self.minimum_overlay_score <= 1.0:
            raise ValueError("minimum_overlay_score must be normalized to 0..1")
        if self.max_overlay_regions <= 0:
            raise ValueError("max_overlay_regions must be positive")
        if not 0.0 <= self.overlay_iou_threshold <= 1.0:
            raise ValueError("overlay_iou_threshold must be normalized to 0..1")
        if self.delogo_padding < 0:
            raise ValueError("delogo_padding cannot be negative")


@dataclass(frozen=True)
class PreviewRestorationPlan:
    evidence: tuple[DetectionEvidence, ...]
    regions: tuple[OverlayRegion, ...]
    overlay_filter: str
    color_filter: str

    @property
    def filtergraph(self) -> str:
        return ",".join(part for part in (self.overlay_filter, self.color_filter) if part)

    @property
    def has_overlay_work(self) -> bool:
        return bool(self.regions)

    @property
    def has_color_work(self) -> bool:
        return bool(self.color_filter)

    @property
    def has_work(self) -> bool:
        return self.has_overlay_work or self.has_color_work


def build_preview_restoration_plan(
    evidence: tuple[DetectionEvidence, ...],
    *,
    frame_width: int,
    frame_height: int,
    color: RestorationColorControls = RestorationColorControls(),
    policy: PreviewRestorationPolicy = PreviewRestorationPolicy(),
) -> PreviewRestorationPlan:
    """Build a deterministic Preview restoration plan from detector evidence."""

    regions = select_overlay_candidates(
        evidence,
        minimum_score=policy.minimum_overlay_score,
        max_regions=policy.max_overlay_regions,
        iou_threshold=policy.overlay_iou_threshold,
    )
    overlay_filter = build_overlay_removal_filtergraph(
        regions,
        frame_width=frame_width,
        frame_height=frame_height,
        padding=policy.delogo_padding,
    )
    return PreviewRestorationPlan(
        evidence=evidence,
        regions=regions,
        overlay_filter=overlay_filter,
        color_filter=build_restoration_color_filter(color),
    )


def inspect_and_plan_preview_restoration(
    ffmpeg: str,
    path: Path,
    *,
    frame_width: int,
    frame_height: int,
    sampling: OverlaySamplingPolicy = OverlaySamplingPolicy(),
    color: RestorationColorControls = RestorationColorControls(),
    policy: PreviewRestorationPolicy = PreviewRestorationPolicy(),
) -> PreviewRestorationPlan:
    """Inspect one source and create a bounded Preview-only restoration plan."""

    evidence = inspect_video_for_overlays(ffmpeg, path, policy=sampling)
    return build_preview_restoration_plan(
        evidence,
        frame_width=frame_width,
        frame_height=frame_height,
        color=color,
        policy=policy,
    )
