"""Pure quality/output decision helpers for the CinePulse UX MegaPack.

The calculations in this module are intentionally advisory.  They expose
relative workload, output-size and VRAM guidance without pretending to know an
exact render time for hardware that has not been benchmarked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..preflight import quality_warnings


@dataclass(frozen=True)
class QualityImpact:
    scale_ratio: float
    fps_ratio: float
    pixel_throughput_ratio: float
    workload_score: float
    workload_label: str
    bitrate_mbps: int
    output_gb: float | None
    vram_reference_gb: float | None
    warnings: tuple[str, ...]


def estimated_bitrate_mbps(width: int, height: int, fps: int) -> int:
    pixels_ratio = max(1.0 / 16.0, width * height / (1920 * 1080))
    return max(8, min(600, round(12 * pixels_ratio * max(1, fps / 60))))


def workload_label(score: float) -> str:
    if score <= 1.2:
        return "Leve"
    if score <= 4.0:
        return "Moderada"
    if score <= 10.0:
        return "Alta"
    if score <= 24.0:
        return "Muito alta"
    return "Extrema"


def estimate_quality_impact(
    *,
    source_width: int,
    source_height: int,
    source_fps: float,
    duration_seconds: float | None,
    target_width: int,
    target_height: int,
    target_fps: int,
    vram_mb: int | None,
    neural_upscale: bool,
    interpolation: str,
) -> QualityImpact:
    source_width = max(1, int(source_width))
    source_height = max(1, int(source_height))
    source_fps = max(1.0, float(source_fps))
    target_width = max(1, int(target_width))
    target_height = max(1, int(target_height))
    target_fps = max(1, int(target_fps))

    scale_ratio = max(target_width / source_width, target_height / source_height)
    fps_ratio = target_fps / source_fps
    pixel_throughput_ratio = (target_width * target_height * target_fps) / (1920 * 1080 * 60)

    score = pixel_throughput_ratio
    if neural_upscale and scale_ratio > 1.01:
        score *= 2.4
    if target_fps > source_fps + 0.01:
        lowered = interpolation.casefold()
        if "rife" in lowered:
            score *= 1.8
        elif "ffmpeg" in lowered or "suave" in lowered:
            score *= 1.3
        else:
            score *= 1.05

    bitrate = estimated_bitrate_mbps(target_width, target_height, target_fps)
    output_gb = None
    if duration_seconds is not None and duration_seconds > 0:
        output_gb = bitrate * float(duration_seconds) / 8 / 1024 * 1.08

    vram_reference_gb = None
    if neural_upscale:
        megapixels = target_width * target_height / 1_000_000
        suggested_mb = math.ceil(2048 + megapixels * 420)
        vram_reference_gb = suggested_mb / 1024

    warnings = quality_warnings(
        source_width,
        source_height,
        source_fps,
        target_width,
        target_height,
        target_fps,
        vram_mb,
        neural_upscale,
        "rife" in interpolation.casefold(),
    )
    return QualityImpact(
        scale_ratio=scale_ratio,
        fps_ratio=fps_ratio,
        pixel_throughput_ratio=pixel_throughput_ratio,
        workload_score=score,
        workload_label=workload_label(score),
        bitrate_mbps=bitrate,
        output_gb=output_gb,
        vram_reference_gb=vram_reference_gb,
        warnings=warnings,
    )


def scale_description(scale_ratio: float) -> str:
    if scale_ratio < 0.98:
        return f"Redução para {scale_ratio:.2f}× da dimensão de referência"
    if scale_ratio <= 1.02:
        return "Sem ampliação relevante"
    if scale_ratio <= 2.05:
        return f"Ampliação ~{scale_ratio:.1f}×"
    if scale_ratio <= 4.05:
        return f"Ampliação forte ~{scale_ratio:.1f}×"
    return f"Ampliação extrema ~{scale_ratio:.1f}×"


def motion_description(source_fps: float, target_fps: int, interpolation: str) -> str:
    source_fps = max(1.0, float(source_fps))
    target_fps = max(1, int(target_fps))
    ratio = target_fps / source_fps
    if target_fps <= source_fps + 0.01:
        return f"{source_fps:.2f} → {target_fps} fps • não precisa criar quadros extras"
    if "rife" in interpolation.casefold():
        return f"{source_fps:.2f} → {target_fps} fps • ~{ratio:.1f}× quadros • interpolação neural"
    if "repet" in interpolation.casefold():
        return f"{source_fps:.2f} → {target_fps} fps • ~{ratio:.1f}× quadros • repetição rápida"
    return f"{source_fps:.2f} → {target_fps} fps • ~{ratio:.1f}× quadros • movimento FFmpeg"
