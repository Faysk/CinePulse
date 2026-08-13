"""Pré-visualização leve e fiel aos VFX do CinePulse.

O objetivo deste módulo é permitir feedback visual imediato sem disparar o
pipeline pesado de render. Os VFX são gerados pelo MESMO ``StudioFrameGenerator``
utilizado no render final; portanto as miniaturas representam o comportamento
real do motor, não artes promocionais desconectadas.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np

from ..vfx import EFFECT_HEIGHT, EFFECT_WIDTH, StudioFrameGenerator, shape_reactivity

CREATE_NO_WINDOW = 0x08000000 if __import__("os").name == "nt" else 0

DEMO_BANDS = np.asarray((0.72, 0.55, 0.44), dtype=np.float32)
DEMO_LOUDNESS = 0.66
DEMO_ATTACK = 0.48


def demo_reactivity(
    frame_number: int,
    *,
    focus: str = "Graves e batidas",
    smoothing: float = 0.82,
    expression: float = 0.82,
) -> tuple[np.ndarray, float, float]:
    """Return deterministic synthetic music features for interactive previews.

    This intentionally exercises the same ``shape_reactivity`` function used by
    the final VFX path, so focus/smoothing/expression controls have visible and
    truthful influence even before the user asks for a rendered preview.
    """
    frame_count = 360
    frames = np.arange(frame_count, dtype=np.float32)
    t = frames / 60.0
    beat = np.clip(np.sin(math.tau * 1.38 * t), 0, 1) ** 7
    bass = np.clip(0.34 + 0.33 * np.sin(math.tau * 0.72 * t + 0.45) + 0.35 * beat, 0, 1)
    mids = np.clip(0.42 + 0.24 * np.sin(math.tau * 0.47 * t + 1.2) + 0.14 * beat, 0, 1)
    highs = np.clip(0.30 + 0.27 * np.sin(math.tau * 1.11 * t + 2.0) + 0.28 * beat, 0, 1)
    energy = np.column_stack((bass, mids, highs)).astype(np.float32)
    rms = np.clip(bass * 0.46 + mids * 0.34 + highs * 0.20, 0, 1).astype(np.float32)
    onset = np.clip(beat * 1.10, 0, 1).astype(np.float32)
    shaped, loudness, attacks = shape_reactivity(
        energy,
        rms,
        onset,
        focus,
        max(0.0, min(1.0, float(smoothing))),
        max(0.25, min(2.0, float(expression))),
    )
    index = int(frame_number) % frame_count
    return shaped[index], float(loudness[index]), float(attacks[index])


def _hex(value: str) -> tuple[int, int, int]:
    value = value.strip().lstrip("#")
    try:
        if len(value) == 6:
            return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        pass
    return 66, 216, 255


def demo_background(width: int = 640, height: int = 360) -> np.ndarray:
    """Gera um fundo cinematográfico abstrato sem depender de assets externos."""
    width = max(32, int(width))
    height = max(18, int(height))
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    nx = xx / max(1, width - 1)
    ny = yy / max(1, height - 1)

    # Céu: azul profundo -> violeta -> pôr do sol quente no horizonte.
    top = np.asarray((10, 19, 38), dtype=np.float32)
    middle = np.asarray((46, 31, 77), dtype=np.float32)
    horizon = np.asarray((246, 124, 91), dtype=np.float32)
    water = np.asarray((7, 18, 33), dtype=np.float32)

    sky_mix = np.clip(ny / 0.62, 0, 1)
    mid_mix = np.clip(ny / 0.35, 0, 1)
    sky = top[None, None, :] * (1 - mid_mix[..., None]) + middle[None, None, :] * mid_mix[..., None]
    warm = np.exp(-((ny - 0.52) / 0.16) ** 2) * np.exp(-((nx - 0.66) / 0.36) ** 2)
    sky = sky * (1 - warm[..., None] * 0.78) + horizon[None, None, :] * warm[..., None] * 0.78

    # Água abaixo do horizonte, com reflexo horizontal discreto.
    water_mask = ny >= 0.58
    shimmer = 0.5 + 0.5 * np.sin(xx * 0.13 + yy * 0.045)
    water_rgb = water[None, None, :] + shimmer[..., None] * np.asarray((10, 13, 21), dtype=np.float32)
    frame = np.where(water_mask[..., None], water_rgb, sky)

    # Montanhas laterais estilizadas, deixando o centro aberto para os VFX.
    left_height = 0.54 - 0.25 * np.power(np.clip(nx / 0.43, 0, 1), 0.72)
    right_height = 0.53 - 0.22 * np.power(np.clip((1 - nx) / 0.39, 0, 1), 0.74)
    mountains = ((nx < 0.47) & (ny > left_height) & (ny < 0.59)) | ((nx > 0.53) & (ny > right_height) & (ny < 0.59))
    mountain_color = np.asarray((13, 20, 35), dtype=np.float32)
    frame[mountains] = mountain_color

    # Sol e reflexo central-direito.
    sx, sy = width * 0.66, height * 0.49
    dist = np.sqrt(((xx - sx) / (width * 0.06)) ** 2 + ((yy - sy) / (height * 0.06)) ** 2)
    sun = np.clip(1 - dist, 0, 1) ** 2
    frame = frame * (1 - sun[..., None] * 0.58) + np.asarray((255, 222, 166), dtype=np.float32) * sun[..., None] * 0.58
    reflection = np.exp(-((xx - sx) / (width * 0.07)) ** 2) * np.exp(-((ny - 0.72) / 0.22) ** 2) * water_mask
    frame += reflection[..., None] * np.asarray((60, 33, 24), dtype=np.float32)

    # Vinheta discreta para aspecto de preview.
    radius = np.sqrt(((nx - 0.5) / 0.72) ** 2 + ((ny - 0.5) / 0.80) ** 2)
    vignette = np.clip((radius - 0.55) / 0.65, 0, 1) * 0.34
    frame *= (1 - vignette[..., None])
    return np.clip(frame, 0, 255).astype(np.uint8)


def effect_rgba(
    effects: set[str],
    color: str = "#42D8FF",
    intensity: float = 1.0,
    occupancy: float = 0.65,
    *,
    frame_number: int = 96,
    bands: np.ndarray | None = None,
    loudness: float = DEMO_LOUDNESS,
    attack: float = DEMO_ATTACK,
    width: int = EFFECT_WIDTH,
    height: int = EFFECT_HEIGHT,
    fps: float = 60.0,
) -> np.ndarray:
    """Return a target-sized RGBA frame from the same VFX generator as final render."""
    generator = StudioFrameGenerator(
        effects, color, intensity, occupancy, width=width, height=height, fps=fps
    )
    raw = generator.make(frame_number, DEMO_BANDS if bands is None else bands, loudness, attack)
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 4).copy()


def resize_nearest(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize determinístico e barato para previews; não entra no render final."""
    src_h, src_w = image.shape[:2]
    xs = np.minimum((np.arange(width) * src_w / width).astype(np.int32), src_w - 1)
    ys = np.minimum((np.arange(height) * src_h / height).astype(np.int32), src_h - 1)
    return image[ys[:, None], xs[None, :]]


def composite(base_rgb: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    """Composição alpha RGB/RGBA com resize automático do overlay."""
    h, w = base_rgb.shape[:2]
    if overlay_rgba.shape[:2] != (h, w):
        overlay_rgba = resize_nearest(overlay_rgba, w, h)
    alpha = overlay_rgba[..., 3:4].astype(np.float32) / 255.0
    out = base_rgb.astype(np.float32) * (1 - alpha) + overlay_rgba[..., :3].astype(np.float32) * alpha
    return np.clip(out, 0, 255).astype(np.uint8)


def visual_preview(
    effects: set[str],
    color: str,
    intensity: float,
    occupancy: float,
    *,
    base_rgb: np.ndarray | None = None,
    width: int = 640,
    height: int = 360,
    frame_number: int = 96,
    focus: str | None = None,
    smoothing: float = 0.82,
    expression: float = 0.82,
    bands: np.ndarray | None = None,
    loudness: float | None = None,
    attack: float | None = None,
) -> np.ndarray:
    """Gera uma imagem de demonstração composta com os VFX selecionados.

    When ``focus`` is supplied, the preview uses a synthetic music envelope
    passed through the same reactivity shaping used by the render engine.
    """
    base = demo_background(width, height) if base_rgb is None else base_rgb
    if base.shape[:2] != (height, width):
        base = resize_nearest(base, width, height)
    if not effects:
        return base.copy()
    if focus is not None and bands is None:
        bands, generated_loudness, generated_attack = demo_reactivity(
            frame_number, focus=focus, smoothing=smoothing, expression=expression
        )
        if loudness is None:
            loudness = generated_loudness
        if attack is None:
            attack = generated_attack
    overlay = effect_rgba(
        effects,
        color,
        intensity,
        occupancy,
        frame_number=frame_number,
        bands=DEMO_BANDS if bands is None else bands,
        loudness=DEMO_LOUDNESS if loudness is None else loudness,
        attack=DEMO_ATTACK if attack is None else attack,
        width=width,
        height=height,
        fps=60.0,
    )
    return composite(base, overlay)


def effect_thumbnail(effect: str, color: str = "#42D8FF", width: int = 160, height: int = 90) -> np.ndarray:
    """Miniatura fiel de um único efeito para cards de descoberta."""
    base = demo_background(width, height)
    overlay = effect_rgba({effect}, color, 1.0, 0.68, frame_number=112, width=width, height=height, fps=60.0)
    return composite(base, overlay)


def to_ppm_bytes(rgb: np.ndarray) -> bytes:
    """Converte RGB em PPM binário, formato entendido pelo Tk PhotoImage."""
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("A imagem precisa estar em RGB uint8.")
    h, w = rgb.shape[:2]
    return f"P6\n{w} {h}\n255\n".encode("ascii") + rgb.tobytes()


def extract_video_frame(
    ffmpeg: str | None,
    path: str,
    *,
    width: int = 640,
    height: int = 360,
    position: float = 1.0,
    timeout: float = 8.0,
) -> np.ndarray | None:
    """Extrai um frame RGB do vídeo para o preview rápido.

    Falhas são deliberadamente silenciosas para a UX: o chamador pode cair no
    fundo de demonstração sem transformar seleção de arquivo em erro bloqueante.
    """
    if not ffmpeg or not path or not Path(path).is_file():
        return None
    command = [
        str(ffmpeg), "-hide_banner", "-loglevel", "error", "-ss", f"{max(0.0, position):.3f}",
        "-i", path, "-frames:v", "1", "-vf",
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x080B12",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    expected = width * height * 3
    if result.returncode or len(result.stdout) != expected:
        return None
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(height, width, 3).copy()
