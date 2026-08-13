"""Pure helpers for the CinePulse Visual Lab.

This module deliberately contains no Tk widgets.  It provides deterministic
preview imagery and UX metadata that the desktop UI can consume without
coupling the visual editor to the render/orchestration code in ``studio.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .preview import demo_background, resize_nearest, visual_preview


EFFECT_SHORT_NAMES: dict[str, str] = {
    "Aurora": "Aurora",
    "Espectro": "Espectro",
    "Barras arredondadas": "Barras",
    "Onda líquida": "Onda líquida",
    "Círculo mágico": "Círculo",
    "Partículas musicais": "Partículas",
    "Pulso cinematográfico": "Pulso",
    "Energia mágica": "Energia",
}


EFFECT_DESCRIPTIONS: dict[str, str] = {
    "Aurora": "Faixas luminosas fluidas",
    "Espectro": "Barras que seguem a música",
    "Barras arredondadas": "Espectro com desenho suave",
    "Onda líquida": "Ondulações horizontais",
    "Círculo mágico": "Anel e glifos reativos",
    "Partículas musicais": "Partículas que flutuam no ritmo",
    "Pulso cinematográfico": "Batidas, flashes e vinheta",
    "Energia mágica": "Glow móvel e raios de energia",
}

DIRECTION_BUTTONS: tuple[tuple[str, str], ...] = (
    ("Cinematográfica", "Cinematográfica"),
    ("Suave", "Suave e atmosférica"),
    ("Épica", "Energética"),
    ("Minimalista", "Minimalista"),
)

TRANSITION_SHORTLIST: tuple[str, ...] = (
    "Corte seco — original",
    "Dissolver suave",
    "Fade cinematográfico",
    "Radial",
)


@dataclass(frozen=True)
class VisualVariant:
    key: str
    label: str
    hint: str


VISUAL_VARIANTS: tuple[VisualVariant, ...] = (
    VisualVariant("soft", "Mais suave", "Reduz intensidade e expressão"),
    VisualVariant("energy", "Mais energia", "Realça intensidade e ataques"),
    VisualVariant("clean", "Menos partículas", "Remove partículas da mistura"),
    VisualVariant("epic", "Modo épico", "Energia + direção mais agressiva"),
)


def _second_scene(width: int, height: int) -> np.ndarray:
    """Create a deterministic alternate frame used only to explain transitions."""
    base = demo_background(width, height).astype(np.float32)
    # Alternate grading and mirrored geometry make the transition visible without
    # pretending it is a second frame from the user's source media.
    alt = base[:, ::-1].copy()
    alt[..., 0] = np.clip(alt[..., 0] * 0.76 + 26, 0, 255)
    alt[..., 1] = np.clip(alt[..., 1] * 0.92 + 8, 0, 255)
    alt[..., 2] = np.clip(alt[..., 2] * 1.18 + 16, 0, 255)
    return alt.astype(np.uint8)


def transition_thumbnail(label: str, width: int = 150, height: int = 84) -> np.ndarray:
    """Return a semantic 50%-progress illustration for a loop transition.

    The image is intentionally an explanatory thumbnail, not a claim that the
    exact FFmpeg transition has already been rendered.  It mirrors the spatial
    character of the selected transition so users can understand the choice.
    """
    width = max(48, int(width))
    height = max(27, int(height))
    a = demo_background(width, height)
    b = _second_scene(width, height)
    yy, xx = np.mgrid[0:height, 0:width]
    nx = xx / max(1, width - 1)
    ny = yy / max(1, height - 1)

    if label == "Corte seco — original":
        mask = nx >= 0.5
        out = np.where(mask[..., None], b, a)
        seam = np.abs(nx - 0.5) < (1.2 / max(1, width))
        out[seam] = np.asarray((230, 236, 246), dtype=np.uint8)
        return out

    if label == "Dissolver suave":
        return np.clip(a.astype(np.float32) * 0.5 + b.astype(np.float32) * 0.5, 0, 255).astype(np.uint8)

    if label in {"Fade cinematográfico", "Fade para preto", "Fade para branco"}:
        midpoint = np.clip(1.0 - np.abs(nx - 0.5) * 2.0, 0, 1)
        blend = a.astype(np.float32) * (1 - nx[..., None]) + b.astype(np.float32) * nx[..., None]
        target = np.asarray((7, 10, 18), dtype=np.float32)
        if label == "Fade para branco":
            target = np.asarray((245, 247, 250), dtype=np.float32)
        fade = midpoint[..., None] * 0.74
        return np.clip(blend * (1 - fade) + target * fade, 0, 255).astype(np.uint8)

    if label in {"Deslizar para esquerda", "Suave horizontal"}:
        split = int(width * 0.53)
        out = np.empty_like(a)
        out[:, :split] = b[:, width - split :]
        out[:, split:] = a[:, : width - split]
        if label == "Suave horizontal":
            feather = max(2, width // 18)
            lo, hi = max(0, split - feather), min(width, split + feather)
            weights = np.linspace(0, 1, hi - lo, dtype=np.float32)[None, :, None]
            out[:, lo:hi] = np.clip(a[:, lo:hi] * (1 - weights) + b[:, lo:hi] * weights, 0, 255)
        return out.astype(np.uint8)

    if label == "Deslizar para direita":
        split = int(width * 0.47)
        out = np.empty_like(a)
        out[:, :split] = a[:, width - split :]
        out[:, split:] = b[:, : width - split]
        return out

    if label in {"Círculo abrindo", "Círculo fechando", "Radial"}:
        cx, cy = 0.5, 0.5
        radius = np.sqrt(((nx - cx) / 0.78) ** 2 + ((ny - cy) / 0.78) ** 2)
        if label == "Círculo fechando":
            mask = radius > 0.47
        elif label == "Radial":
            angle = (np.arctan2(ny - cy, nx - cx) + np.pi) / (2 * np.pi)
            mask = angle < 0.54
        else:
            mask = radius < 0.47
        return np.where(mask[..., None], b, a)

    if label == "Pixelizar":
        mixed = np.clip(a.astype(np.float32) * 0.42 + b.astype(np.float32) * 0.58, 0, 255).astype(np.uint8)
        small_w, small_h = max(8, width // 12), max(5, height // 12)
        blocky = resize_nearest(resize_nearest(mixed, small_w, small_h), width, height)
        return blocky

    return np.clip(a.astype(np.float32) * 0.5 + b.astype(np.float32) * 0.5, 0, 255).astype(np.uint8)


def variant_preview(
    key: str,
    effects: set[str],
    color: str,
    intensity: float,
    occupancy: float,
    *,
    base_rgb: np.ndarray,
    frame_number: int,
    focus: str,
    smoothing: float,
    expression: float,
    width: int = 220,
    height: int = 124,
) -> np.ndarray:
    """Render one explanatory quick-variation card using the real VFX engine."""
    variant_effects = set(effects)
    variant_intensity = intensity
    variant_occupancy = occupancy
    variant_expression = expression
    variant_focus = focus

    if key == "soft":
        variant_intensity *= 0.72
        variant_expression *= 0.72
    elif key == "energy":
        variant_intensity = min(2.0, variant_intensity * 1.28)
        variant_expression = min(2.0, variant_expression * 1.32)
        variant_focus = "Batidas e ataques"
    elif key == "clean":
        variant_effects.discard("Partículas musicais")
        variant_occupancy *= 0.90
    elif key == "epic":
        variant_effects.add("Energia mágica")
        variant_intensity = min(2.0, variant_intensity * 1.16)
        variant_expression = min(2.0, variant_expression * 1.18)
        variant_focus = "Batidas e ataques"

    return visual_preview(
        variant_effects,
        color,
        variant_intensity,
        variant_occupancy,
        base_rgb=base_rgb,
        width=width,
        height=height,
        frame_number=frame_number,
        focus=variant_focus,
        smoothing=smoothing,
        expression=variant_expression,
    )
