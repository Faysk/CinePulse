"""Preview-only color restoration controls.

The stable color pipeline remains authoritative for HDR/SDR preservation. This
module only describes user-facing restorative adjustments that can be appended
after the working color conversion has already been chosen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RestorationPreset = Literal["neutral", "faded", "flat", "warm", "cool"]


@dataclass(frozen=True)
class RestorationColorControls:
    """Small, bounded adjustments intended for restoration rather than grading."""

    brightness: float = 0.0
    contrast: float = 1.0
    saturation: float = 1.0
    gamma: float = 1.0
    temperature: float = 0.0
    tint: float = 0.0

    def __post_init__(self) -> None:
        bounds = {
            "brightness": (-0.20, 0.20),
            "contrast": (0.70, 1.35),
            "saturation": (0.60, 1.50),
            "gamma": (0.75, 1.35),
            "temperature": (-0.30, 0.30),
            "tint": (-0.25, 0.25),
        }
        for name, (minimum, maximum) in bounds.items():
            value = getattr(self, name)
            if not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric")
            if not minimum <= float(value) <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")

    @property
    def is_neutral(self) -> bool:
        return self == RestorationColorControls()


def preset_controls(preset: RestorationPreset) -> RestorationColorControls:
    """Return conservative starting points for common degraded-source patterns."""

    presets: dict[RestorationPreset, RestorationColorControls] = {
        "neutral": RestorationColorControls(),
        "faded": RestorationColorControls(contrast=1.10, saturation=1.12, gamma=0.98),
        "flat": RestorationColorControls(contrast=1.08, saturation=1.06),
        "warm": RestorationColorControls(temperature=0.08, saturation=1.03),
        "cool": RestorationColorControls(temperature=-0.08, saturation=1.03),
    }
    try:
        return presets[preset]
    except KeyError as exc:
        raise ValueError(f"unknown restoration preset: {preset}") from exc


def _clean(value: float) -> str:
    text = f"{float(value):.5f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def build_restoration_color_filter(controls: RestorationColorControls) -> str:
    """Build a deterministic FFmpeg filter for SDR restoration adjustments.

    Temperature and tint are intentionally implemented with bounded RGB channel
    gains instead of LUTs so the Preview path stays local and dependency-free.
    The filter does not attach or rewrite color metadata; the core ColorPipeline
    remains responsible for that contract.
    """

    if controls.is_neutral:
        return ""

    filters: list[str] = []
    if any(
        abs(value - neutral) > 1e-9
        for value, neutral in (
            (controls.brightness, 0.0),
            (controls.contrast, 1.0),
            (controls.saturation, 1.0),
            (controls.gamma, 1.0),
        )
    ):
        filters.append(
            "eq="
            f"brightness={_clean(controls.brightness)}:"
            f"contrast={_clean(controls.contrast)}:"
            f"saturation={_clean(controls.saturation)}:"
            f"gamma={_clean(controls.gamma)}"
        )

    if abs(controls.temperature) > 1e-9 or abs(controls.tint) > 1e-9:
        red = 1.0 + controls.temperature * 0.18 + controls.tint * 0.05
        green = 1.0 - controls.tint * 0.14
        blue = 1.0 - controls.temperature * 0.18 + controls.tint * 0.05
        filters.append(
            "colorchannelmixer="
            f"rr={_clean(red)}:gg={_clean(green)}:bb={_clean(blue)}:"
            "aa=1"
        )

    return ",".join(filters)
