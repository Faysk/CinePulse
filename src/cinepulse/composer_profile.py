from __future__ import annotations

"""Shared base-video contract for the Preview Overlay Composer.

This module is deliberately dependency-light so probing and exporting can share
one exact color/timing contract without importing each other.
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
