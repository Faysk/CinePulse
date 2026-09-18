from __future__ import annotations

"""Shared base-media contract for the Preview Overlay Composer.

The Composer can use either a video or a still image as its visual base.  A
still image receives timing from the project audio/output settings while the
final render keeps the same deterministic SDR BT.709 reference contract.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComposerBaseProfile:
    width: int
    height: int
    fps: float
    duration: float
    pixel_format: str
    primaries: str
    transfer: str
    matrix: str
    color_range: str
    still_image: bool = False

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.fps <= 0 or self.duration <= 0:
            raise ValueError("composer base dimensions/timing must be positive")

    @property
    def reference_supported(self) -> bool:
        """Fail closed outside the proven SDR BT.709 8-bit CPU reference."""
        pix = self.pixel_format.strip().lower()
        transfer = self.transfer.strip().lower()
        primaries = self.primaries.strip().lower()
        matrix = self.matrix.strip().lower()
        return (
            not any(token in pix for token in ("10", "12", "16", "p010", "p016"))
            and transfer in {"bt709", "iec61966-2-1", "unknown", ""}
            and primaries in {"bt709", "unknown", ""}
            and matrix in {"bt709", "unknown", ""}
        )
