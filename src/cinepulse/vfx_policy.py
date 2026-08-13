from __future__ import annotations

import math
from dataclasses import dataclass

# Phase 3 removes the legacy fixed 320x180/60 canvas.  VFX are rendered at the
# actual target cadence up to 120 fps and at native spatial resolution up to 4K.
# Above 4K, the layer remains target-aware but uses a 4K-class working canvas to
# avoid pathological CPU/RAM/raw-pipe pressure in the current NumPy renderer.
MAX_VFX_PIXELS = 3840 * 2160
MAX_VFX_FPS = 120.0
MIN_VFX_EDGE = 64


@dataclass(frozen=True)
class VfxRenderSpec:
    width: int
    height: int
    fps: float
    native_spatial: bool
    native_temporal: bool

    @property
    def scale(self) -> float:
        return 1.0

    @property
    def label(self) -> str:
        suffixes: list[str] = []
        if not self.native_spatial:
            suffixes.append("canvas adaptativo 4K")
        if not self.native_temporal:
            suffixes.append("amostragem temporal limitada")
        suffix = "" if not suffixes else " • " + " • ".join(suffixes)
        return f"{self.width}×{self.height} • {self.fps:g} fps{suffix}"


def _even(value: float) -> int:
    rounded = max(MIN_VFX_EDGE, int(round(value)))
    return rounded if rounded % 2 == 0 else rounded - 1


def choose_vfx_render_spec(output_width: int, output_height: int, output_fps: float) -> VfxRenderSpec:
    """Choose a target-aware VFX working canvas.

    * <= 4K: native output dimensions.
    * > 4K: same aspect ratio, capped to a 4K-class pixel budget.
    * <= 120 fps: native cadence.
    * > 120 fps: 120 fps analysis/render sampling; the base video retains its
      own cadence and FFmpeg timestamps synchronize the overlay.

    This is deliberately deterministic so RenderPlan, worker, logs and tests
    all describe the same VFX geometry.
    """

    if min(output_width, output_height) <= 0 or output_fps <= 0:
        raise ValueError("VFX output dimensions/FPS must be positive.")

    output_pixels = output_width * output_height
    if output_pixels <= MAX_VFX_PIXELS:
        width, height = int(output_width), int(output_height)
        native_spatial = True
    else:
        ratio = math.sqrt(MAX_VFX_PIXELS / output_pixels)
        width = _even(output_width * ratio)
        height = _even(output_height * ratio)
        # Rounding can exceed the budget by a tiny amount; trim the dominant edge.
        while width * height > MAX_VFX_PIXELS:
            if width >= height:
                width = max(MIN_VFX_EDGE, width - 2)
            else:
                height = max(MIN_VFX_EDGE, height - 2)
        native_spatial = False

    fps = min(float(output_fps), MAX_VFX_FPS)
    return VfxRenderSpec(
        width=width,
        height=height,
        fps=fps,
        native_spatial=native_spatial,
        native_temporal=output_fps <= MAX_VFX_FPS + 0.01,
    )
