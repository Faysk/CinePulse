"""Preview-only delivery guardrails for restoration experiments.

This module does not change Stable render policy.  It describes whether an
experimental Preview target is structurally supportable, what its memory
pressure looks like, and which claims still require a physical hardware run.
"""

from __future__ import annotations

from dataclasses import dataclass


MAX_PREVIEW_WIDTH = 11520
MAX_PREVIEW_HEIGHT = 6480
MAX_PREVIEW_FPS = 120


@dataclass(frozen=True)
class PreviewDeliveryTarget:
    width: int
    height: int
    fps: float
    bit_depth: int = 10

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("preview delivery dimensions must be positive")
        if self.fps <= 0:
            raise ValueError("preview delivery fps must be positive")
        if self.bit_depth not in {8, 10, 12, 16}:
            raise ValueError("unsupported preview bit depth")

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def megapixels(self) -> float:
        return self.pixels / 1_000_000.0

    @property
    def is_8k_or_higher(self) -> bool:
        return self.width >= 7680 or self.height >= 4320

    @property
    def is_12k(self) -> bool:
        return self.width >= 11520 or self.height >= 6480


@dataclass(frozen=True)
class PreviewDeliveryAssessment:
    allowed: bool
    target: PreviewDeliveryTarget
    estimated_rgb_frame_mib: float
    estimated_working_set_mib: float
    requires_physical_acceptance: bool
    warnings: tuple[str, ...]


def estimate_frame_mib(target: PreviewDeliveryTarget, *, channels: int = 3) -> float:
    """Estimate one unpacked RGB frame, rounded only by the caller for display."""

    if channels <= 0:
        raise ValueError("channels must be positive")
    bytes_per_channel = 1 if target.bit_depth <= 8 else 2
    return target.pixels * channels * bytes_per_channel / (1024.0 * 1024.0)


def assess_preview_delivery(
    target: PreviewDeliveryTarget,
    *,
    temporal_window: int = 5,
    has_real_gpu_evidence: bool = False,
    scratch_free_gib: float | None = None,
) -> PreviewDeliveryAssessment:
    """Return conservative Preview-only feasibility and acceptance metadata.

    Structural support is intentionally different from physical acceptance.
    A target can be allowed for experimentation while still requiring a real
    GPU run before release notes or UI badges may call it validated.
    """

    if temporal_window < 1:
        raise ValueError("temporal_window must be >= 1")

    warnings: list[str] = []
    allowed = True

    if target.width > MAX_PREVIEW_WIDTH or target.height > MAX_PREVIEW_HEIGHT:
        allowed = False
        warnings.append("Target exceeds the Preview 12K spatial envelope.")
    if target.fps > MAX_PREVIEW_FPS:
        allowed = False
        warnings.append("Target exceeds the Preview 120 fps envelope.")

    frame_mib = estimate_frame_mib(target)
    # Temporal reconstruction needs source/destination plus donor frames.  This
    # is a planning floor, not a VRAM promise: codecs and AI backends add more.
    working_set_mib = frame_mib * (temporal_window + 2)

    if working_set_mib >= 4096:
        warnings.append("Temporal RGB working set alone exceeds 4 GiB; chunking is mandatory.")
    elif working_set_mib >= 2048:
        warnings.append("Temporal RGB working set is heavy; use bounded chunks and scratch storage.")

    if scratch_free_gib is not None:
        if scratch_free_gib < 0:
            raise ValueError("scratch_free_gib cannot be negative")
        # Keep this deliberately coarse. It protects obvious foot-guns without
        # pretending to predict encoded output size or model caches precisely.
        minimum_gib = max(2.0, working_set_mib / 1024.0 * 3.0)
        if scratch_free_gib < minimum_gib:
            allowed = False
            warnings.append(
                f"Scratch space is too low for the planned working set; need about {minimum_gib:.1f} GiB free."
            )

    needs_physical = target.is_8k_or_higher or target.fps > 60
    if needs_physical and not has_real_gpu_evidence:
        warnings.append("Physical GPU acceptance is still pending for this target.")

    return PreviewDeliveryAssessment(
        allowed=allowed,
        target=target,
        estimated_rgb_frame_mib=frame_mib,
        estimated_working_set_mib=working_set_mib,
        requires_physical_acceptance=needs_physical and not has_real_gpu_evidence,
        warnings=tuple(warnings),
    )
