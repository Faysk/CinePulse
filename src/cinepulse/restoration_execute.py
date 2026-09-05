"""Preview-only restoration execution helpers.

The Stable render pipeline intentionally does not import this module. Preview
orchestration may use temporal reconstruction when decoded RGB frames are
available and otherwise fall back to the deterministic FFmpeg filtergraph from
``PreviewRestorationPlan``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .restoration_inpaint import TemporalReconstructionPolicy, reconstruct_region_temporally
from .restoration_preview import PreviewRestorationPlan


@dataclass(frozen=True)
class TemporalExecutionReport:
    frames: tuple[np.ndarray, ...]
    attempted_regions: int
    applied_regions: int
    fallback_regions: int
    mean_confidence: float

    @property
    def used_temporal_reconstruction(self) -> bool:
        return self.applied_regions > 0


def apply_temporal_reconstruction(
    frames: Sequence[np.ndarray],
    plan: PreviewRestorationPlan,
    *,
    policy: TemporalReconstructionPolicy = TemporalReconstructionPolicy(),
) -> TemporalExecutionReport:
    """Apply the selected Preview overlay regions across an RGB frame sequence.

    Each region is reconstructed independently per target frame. A rejected
    temporal attempt leaves that region untouched so the caller can route those
    cases through the plan's FFmpeg ``delogo`` fallback instead of inventing
    pixels with low confidence.
    """

    if not frames:
        raise ValueError("at least one frame is required")
    working = [np.asarray(frame).copy() for frame in frames]
    shape = working[0].shape
    if len(shape) != 3 or shape[2] != 3:
        raise ValueError("Preview temporal execution expects RGB HxWx3 frames")
    if any(frame.shape != shape for frame in working):
        raise ValueError("Preview temporal execution frames must share dimensions")

    attempted = 0
    applied = 0
    confidences: list[float] = []
    for target_index in range(len(working)):
        for region in plan.regions:
            attempted += 1
            # Donors must come from the state before this target frame is
            # modified, otherwise reconstructed pixels could recursively become
            # evidence for later patches in the same frame sequence.
            result = reconstruct_region_temporally(
                frames,
                target_index=target_index,
                region=region,
                policy=policy,
            )
            if not result.applied:
                continue
            working[target_index] = result.frame
            applied += 1
            confidences.append(result.confidence)

    fallback = attempted - applied
    mean_confidence = float(np.mean(confidences)) if confidences else 0.0
    return TemporalExecutionReport(
        frames=tuple(working),
        attempted_regions=attempted,
        applied_regions=applied,
        fallback_regions=fallback,
        mean_confidence=mean_confidence,
    )


def build_preview_ffmpeg_command(
    ffmpeg: str,
    source: Path,
    output: Path,
    plan: PreviewRestorationPlan,
    *,
    video_codec: str = "libx264",
    crf: int = 16,
    preset: str = "slow",
) -> list[str]:
    """Build a conservative Preview render command from one restoration plan.

    Audio is copied when present. The caller owns temporary/output policy and
    may swap the codec after checking local FFmpeg capabilities. This helper is
    deliberately Preview-only and never changes Stable delivery decisions.
    """

    if not ffmpeg:
        raise ValueError("ffmpeg executable is required")
    if not 0 <= int(crf) <= 51:
        raise ValueError("crf must be between 0 and 51")

    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-i",
        str(source),
    ]
    if plan.filtergraph:
        command.extend(["-vf", plan.filtergraph])
    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            video_codec,
            "-preset",
            preset,
            "-crf",
            str(int(crf)),
            "-c:a",
            "copy",
            str(output),
        ]
    )
    return command
