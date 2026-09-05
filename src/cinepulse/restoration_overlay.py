"""Preview-only primitives for removing burned-in overlays from video.

The module intentionally has no optional CV dependency. Detection backends can
feed normalized evidence into this core while CinePulse keeps scoring,
non-max-suppression and FFmpeg reconstruction deterministic and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal


OverlayKind = Literal["text", "qr", "logo", "unknown"]


@dataclass(frozen=True)
class OverlayRegion:
    """Normalized overlay rectangle, expressed in source-frame coordinates."""

    x: float
    y: float
    width: float
    height: float
    kind: OverlayKind = "unknown"
    confidence: float = 0.0

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height, self.confidence)
        if not all(isinstance(value, (int, float)) for value in values):
            raise TypeError("overlay region values must be numeric")
        if not 0.0 <= self.x <= 1.0 or not 0.0 <= self.y <= 1.0:
            raise ValueError("overlay origin must be normalized to 0..1")
        if not 0.0 < self.width <= 1.0 or not 0.0 < self.height <= 1.0:
            raise ValueError("overlay size must be normalized to 0..1")
        if self.x + self.width > 1.0 + 1e-9 or self.y + self.height > 1.0 + 1e-9:
            raise ValueError("overlay region extends outside the frame")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be normalized to 0..1")

    @property
    def area(self) -> float:
        return self.width * self.height

    def to_pixels(self, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("frame dimensions must be positive")
        x = min(frame_width - 1, max(0, round(self.x * frame_width)))
        y = min(frame_height - 1, max(0, round(self.y * frame_height)))
        width = max(1, round(self.width * frame_width))
        height = max(1, round(self.height * frame_height))
        width = min(width, frame_width - x)
        height = min(height, frame_height - y)
        return x, y, width, height


@dataclass(frozen=True)
class DetectionEvidence:
    """Backend-independent evidence for a suspected non-source overlay."""

    region: OverlayRegion
    persistence: float
    edge_density: float
    temporal_stability: float
    text_confidence: float = 0.0
    qr_confidence: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "persistence",
            "edge_density",
            "temporal_stability",
            "text_confidence",
            "qr_confidence",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be normalized to 0..1")

    @property
    def score(self) -> float:
        """Conservative confidence score for burned-in overlay likelihood.

        Persistence and temporal stability dominate because static UI/text tends
        to remain anchored while source imagery moves. OCR/QR confidence can
        promote a candidate, but cannot by itself overpower weak temporal proof.
        """

        semantic = max(self.text_confidence, self.qr_confidence)
        score = (
            self.persistence * 0.34
            + self.temporal_stability * 0.30
            + self.edge_density * 0.14
            + semantic * 0.22
        )
        return max(0.0, min(1.0, score))

    def classified_region(self) -> OverlayRegion:
        kind: OverlayKind = self.region.kind
        if self.qr_confidence >= 0.55 and self.qr_confidence >= self.text_confidence:
            kind = "qr"
        elif self.text_confidence >= 0.45:
            kind = "text"
        return OverlayRegion(
            x=self.region.x,
            y=self.region.y,
            width=self.region.width,
            height=self.region.height,
            kind=kind,
            confidence=self.score,
        )


def _intersection_over_union(left: OverlayRegion, right: OverlayRegion) -> float:
    x1 = max(left.x, right.x)
    y1 = max(left.y, right.y)
    x2 = min(left.x + left.width, right.x + right.width)
    y2 = min(left.y + left.height, right.y + right.height)
    width = max(0.0, x2 - x1)
    height = max(0.0, y2 - y1)
    intersection = width * height
    if intersection <= 0:
        return 0.0
    union = left.area + right.area - intersection
    return intersection / union if union > 0 else 0.0


def select_overlay_candidates(
    evidence: Iterable[DetectionEvidence],
    *,
    minimum_score: float = 0.62,
    max_regions: int = 8,
    iou_threshold: float = 0.45,
) -> tuple[OverlayRegion, ...]:
    """Score, classify and deduplicate detector candidates.

    Large regions are deliberately rejected by default because automated
    reconstruction should not silently erase meaningful source content.
    """

    if not 0.0 <= minimum_score <= 1.0:
        raise ValueError("minimum_score must be normalized to 0..1")
    if max_regions <= 0:
        raise ValueError("max_regions must be positive")
    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("iou_threshold must be normalized to 0..1")

    ranked = [item.classified_region() for item in evidence if item.score >= minimum_score]
    ranked = [region for region in ranked if region.area <= 0.20]
    ranked.sort(key=lambda region: (region.confidence, -region.area), reverse=True)

    selected: list[OverlayRegion] = []
    for candidate in ranked:
        if any(_intersection_over_union(candidate, kept) >= iou_threshold for kept in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_regions:
            break
    return tuple(selected)


def build_delogo_filters(
    regions: Iterable[OverlayRegion],
    *,
    frame_width: int,
    frame_height: int,
    padding: int = 6,
) -> tuple[str, ...]:
    """Build bounded FFmpeg ``delogo`` filters for a Preview reconstruction pass.

    ``delogo`` is intentionally the first reconstruction backend: it is local,
    deterministic, cancellable with the existing FFmpeg process controls and
    works without shipping a heavyweight model. Later Preview phases can replace
    it with temporal/AI inpainting while retaining the same region contract.
    """

    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame dimensions must be positive")
    if padding < 0:
        raise ValueError("padding cannot be negative")

    filters: list[str] = []
    for region in regions:
        x, y, width, height = region.to_pixels(frame_width, frame_height)
        left = max(0, x - padding)
        top = max(0, y - padding)
        right = min(frame_width, x + width + padding)
        bottom = min(frame_height, y + height + padding)
        padded_width = right - left
        padded_height = bottom - top
        filters.append(f"delogo=x={left}:y={top}:w={padded_width}:h={padded_height}:show=0")
    return tuple(filters)


def build_overlay_removal_filtergraph(
    regions: Iterable[OverlayRegion],
    *,
    frame_width: int,
    frame_height: int,
    padding: int = 6,
) -> str:
    """Return a comma-separated Preview filtergraph or an empty string."""

    return ",".join(
        build_delogo_filters(
            regions,
            frame_width=frame_width,
            frame_height=frame_height,
            padding=padding,
        )
    )
