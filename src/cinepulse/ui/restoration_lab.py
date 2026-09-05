"""Pure UI helpers for the Preview-only restoration lab.

The desktop shell can consume this module without pulling detector/FFmpeg work
onto Tk's event thread.  Stable render planning is intentionally untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..restoration_color import RestorationColorControls, RestorationPreset, preset_controls
from ..restoration_preview import PreviewRestorationPlan


RESTORATION_PRESETS: tuple[tuple[RestorationPreset, str, str], ...] = (
    ("neutral", "Neutro", "Sem correção adicional"),
    ("faded", "Desbotado", "Recupera contraste e saturação com cuidado"),
    ("flat", "Sem vida", "Realce leve para fontes muito planas"),
    ("warm", "Mais quente", "Aquece discretamente sem mudar o contrato de cor"),
    ("cool", "Mais frio", "Esfria discretamente sem mudar o contrato de cor"),
)


@dataclass(frozen=True)
class RestorationUiState:
    remove_overlays: bool = False
    preset: RestorationPreset = "neutral"
    brightness: float | None = None
    contrast: float | None = None
    saturation: float | None = None
    gamma: float | None = None
    temperature: float | None = None
    tint: float | None = None

    def controls(self) -> RestorationColorControls:
        base = preset_controls(self.preset)
        values = {
            "brightness": base.brightness if self.brightness is None else float(self.brightness),
            "contrast": base.contrast if self.contrast is None else float(self.contrast),
            "saturation": base.saturation if self.saturation is None else float(self.saturation),
            "gamma": base.gamma if self.gamma is None else float(self.gamma),
            "temperature": base.temperature if self.temperature is None else float(self.temperature),
            "tint": base.tint if self.tint is None else float(self.tint),
        }
        return RestorationColorControls(**values)


def analysis_summary(plan: PreviewRestorationPlan | None, *, analyzing: bool = False, error: str | None = None) -> str:
    """Human-facing one-line status for the restoration card."""

    if analyzing:
        return "Analisando frames para textos, QR codes e overlays persistentes…"
    if error:
        return f"Análise indisponível: {error}"
    if plan is None:
        return "Análise ainda não executada. A remoção automática continua desligada."
    count = len(plan.regions)
    if count == 0:
        return "Nenhum overlay seguro foi encontrado; a imagem original será preservada."
    noun = "região segura" if count == 1 else "regiões seguras"
    return f"{count} {noun} para remoção automática. Revise o preview antes de exportar."


def _clip_rgb(value: np.ndarray) -> np.ndarray:
    return np.clip(value, 0.0, 255.0)


def color_preview(rgb: np.ndarray, controls: RestorationColorControls) -> np.ndarray:
    """Fast NumPy approximation of the bounded restoration controls for UI preview.

    This is deliberately presentation-only; final output still uses the FFmpeg
    filtergraph from ``restoration_color`` so render semantics remain explicit.
    """

    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("restoration preview expects an RGB HxWx3 image")
    if image.dtype != np.uint8:
        image = _clip_rgb(image.astype(np.float32)).astype(np.uint8)
    if controls.is_neutral:
        return image.copy()

    out = image.astype(np.float32) / 255.0
    out = (out - 0.5) * controls.contrast + 0.5 + controls.brightness

    luma = out[..., 0] * 0.2126 + out[..., 1] * 0.7152 + out[..., 2] * 0.0722
    out = luma[..., None] + (out - luma[..., None]) * controls.saturation
    out = np.clip(out, 0.0, 1.0) ** (1.0 / controls.gamma)

    red = 1.0 + controls.temperature * 0.18 + controls.tint * 0.05
    green = 1.0 - controls.tint * 0.14
    blue = 1.0 - controls.temperature * 0.18 + controls.tint * 0.05
    out *= np.asarray((red, green, blue), dtype=np.float32)
    return np.clip(out * 255.0, 0.0, 255.0).astype(np.uint8)


def overlay_boxes_preview(rgb: np.ndarray, plan: PreviewRestorationPlan | None) -> np.ndarray:
    """Draw conservative candidate boxes for review without modifying source pixels."""

    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("overlay preview expects an RGB HxWx3 image")
    result = image.astype(np.uint8, copy=True)
    if plan is None or not plan.regions:
        return result

    height, width = result.shape[:2]
    marker = np.asarray((255, 214, 64), dtype=np.uint8)
    for region in plan.regions:
        x1 = max(0, min(width - 1, int(round(region.x * width))))
        y1 = max(0, min(height - 1, int(round(region.y * height))))
        x2 = max(x1 + 1, min(width, int(round((region.x + region.width) * width))))
        y2 = max(y1 + 1, min(height, int(round((region.y + region.height) * height))))
        thickness = max(1, min(width, height) // 180)
        result[y1 : min(y1 + thickness, y2), x1:x2] = marker
        result[max(y2 - thickness, y1) : y2, x1:x2] = marker
        result[y1:y2, x1 : min(x1 + thickness, x2)] = marker
        result[y1:y2, max(x2 - thickness, x1) : x2] = marker
    return result
