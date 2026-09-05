from __future__ import annotations

"""Backend-neutral geometry for Preview music visualizers.

The CPU renderer and any future evidence-gated GPU shader must consume these
same normalized primitives. Keeping geometry pure prevents preview/final drift
and makes visual-parity benchmarking possible without binding the contract to a
specific graphics API.
"""

from dataclasses import dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Bar:
    x0: float
    y0: float
    x1: float
    y1: float
    amplitude: float


@dataclass(frozen=True)
class RadialBar:
    inner: Point
    outer: Point
    amplitude: float


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _values(values: Iterable[float], *, minimum: int = 1) -> tuple[float, ...]:
    result = tuple(_clamp(value) for value in values)
    if len(result) < minimum:
        return tuple(0.0 for _ in range(minimum))
    return result


def waveform_points(values: Iterable[float], *, reaction: float = 1.0) -> tuple[Point, ...]:
    """Return normalized waveform points centered at y=.5.

    Input is expected to be an already-smoothed envelope/sample slice in 0..1.
    ``reaction`` can only attenuate/amplify inside the normalized viewport; the
    geometry never escapes 0..1 even for corrupted upstream values.
    """
    samples = _values(values, minimum=2)
    gain = max(0.0, min(2.0, float(reaction)))
    denominator = max(1, len(samples) - 1)
    return tuple(
        Point(index / denominator, _clamp(0.5 + (sample - 0.5) * gain))
        for index, sample in enumerate(samples)
    )


def spectrum_bars(values: Iterable[float], *, reaction: float = 1.0, gap: float = 0.12) -> tuple[Bar, ...]:
    """Return bottom-anchored normalized frequency bars."""
    bands = _values(values)
    gain = max(0.0, min(2.0, float(reaction)))
    gap_ratio = max(0.0, min(0.8, float(gap)))
    width = 1.0 / len(bands)
    inset = width * gap_ratio * 0.5
    result: list[Bar] = []
    for index, value in enumerate(bands):
        amplitude = _clamp(value * gain)
        x0 = index * width + inset
        x1 = (index + 1) * width - inset
        result.append(Bar(x0, 1.0 - amplitude, x1, 1.0, amplitude))
    return tuple(result)


def circular_bars(
    values: Iterable[float],
    *,
    reaction: float = 1.0,
    inner_radius: float = 0.24,
    radial_span: float = 0.24,
    rotation_degrees: float = 0.0,
) -> tuple[RadialBar, ...]:
    """Return radial bars around normalized center (.5,.5)."""
    bands = _values(values, minimum=8)
    gain = max(0.0, min(2.0, float(reaction)))
    inner = max(0.01, min(0.48, float(inner_radius)))
    span = max(0.0, min(0.50 - inner, float(radial_span)))
    rotation = math.radians(float(rotation_degrees))
    result: list[RadialBar] = []
    for index, value in enumerate(bands):
        amplitude = _clamp(value * gain)
        angle = rotation + 2.0 * math.pi * index / len(bands)
        outer_radius = inner + span * amplitude
        cosine, sine = math.cos(angle), math.sin(angle)
        result.append(
            RadialBar(
                Point(0.5 + inner * cosine, 0.5 + inner * sine),
                Point(0.5 + outer_radius * cosine, 0.5 + outer_radius * sine),
                amplitude,
            )
        )
    return tuple(result)


def geometry_for(kind: str, values: Iterable[float], *, reaction: float = 1.0, rotation_degrees: float = 0.0) -> object:
    if kind == "waveform":
        return waveform_points(values, reaction=reaction)
    if kind == "spectrum":
        return spectrum_bars(values, reaction=reaction)
    if kind == "circular":
        return circular_bars(values, reaction=reaction, rotation_degrees=rotation_degrees)
    raise ValueError(f"unsupported visualizer geometry kind: {kind}")
