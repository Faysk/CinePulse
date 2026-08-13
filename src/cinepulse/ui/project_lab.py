"""Pure helpers for the CinePulse Project workspace.

This module intentionally contains no Tk code.  It converts FFprobe payloads
into compact user-facing summaries and builds an inexpensive framing preview
that mirrors the geometry used by the render pipeline (cover = scale+crop,
contain = scale+pad).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..media_profile import ColorProfile
from ..preflight import validate_output_path
from .preview import resize_nearest


@dataclass(frozen=True)
class MediaSummary:
    headline: str
    detail: str
    badge: str


def _duration_seconds(data: dict) -> float:
    try:
        return max(0.0, float((data.get("format") or {}).get("duration") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def format_duration_short(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _rate(value: object) -> float:
    text = str(value or "0")
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            return float(numerator) / max(float(denominator), 1e-9)
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _stream(data: dict, kind: str) -> dict:
    return next((item for item in data.get("streams", []) if item.get("codec_type") == kind), {})


def _codec_label(stream: dict) -> str:
    codec = str(stream.get("codec_name") or "codec desconhecido").upper()
    profile = str(stream.get("profile") or "").strip()
    if profile and profile.casefold() not in {"unknown", "none"}:
        return f"{codec} {profile}"
    return codec


def summarize_video_probe(data: dict) -> MediaSummary:
    video = _stream(data, "video")
    if not video or not video.get("width") or not video.get("height"):
        raise ValueError("O arquivo não contém uma faixa de vídeo utilizável.")
    width = int(video["width"])
    height = int(video["height"])
    fps = _rate(video.get("avg_frame_rate") or video.get("r_frame_rate"))
    duration = _duration_seconds(data)
    profile = ColorProfile.from_probe(data)
    audio = _stream(data, "audio")
    audio_text = "sem áudio"
    if audio:
        channels = int(audio.get("channels") or 0)
        channel_text = "mono" if channels == 1 else "estéreo" if channels == 2 else f"{channels} canais" if channels else "áudio"
        sample_rate = int(float(audio.get("sample_rate") or 0))
        sample_text = f" • {sample_rate / 1000:g} kHz" if sample_rate else ""
        audio_text = f"{_codec_label(audio)} • {channel_text}{sample_text}"
    headline = f"{width}×{height} • {fps:.2f} fps • {format_duration_short(duration)}"
    detail = f"{_codec_label(video)} • {profile.label} • {audio_text}"
    return MediaSummary(headline, detail, "Vídeo analisado")


def summarize_audio_probe(data: dict) -> MediaSummary:
    audio = _stream(data, "audio")
    if not audio:
        raise ValueError("O arquivo não contém uma faixa de áudio utilizável.")
    duration = _duration_seconds(data)
    channels = int(audio.get("channels") or 0)
    channel_text = "mono" if channels == 1 else "estéreo" if channels == 2 else f"{channels} canais" if channels else "canais não informados"
    sample_rate = int(float(audio.get("sample_rate") or 0))
    bitrate = int(float(audio.get("bit_rate") or 0))
    sample_text = f"{sample_rate / 1000:g} kHz" if sample_rate else "sample rate não informado"
    bitrate_text = f" • {bitrate / 1000:.0f} kb/s" if bitrate else ""
    headline = f"{format_duration_short(duration)} • {_codec_label(audio)} • {sample_text}"
    detail = f"{channel_text}{bitrate_text}"
    return MediaSummary(headline, detail, "Áudio analisado")


def output_state(output: str, video: str = "", audio: str = "") -> tuple[str, str, str]:
    """Return (state, title, detail) for lightweight inline output validation."""
    if not output.strip():
        return "pending", "Escolha onde salvar", "O CinePulse só precisa desse destino para o render final; previews usam a pasta interna."
    path = Path(output).expanduser()
    errors = validate_output_path(path, tuple(Path(value) for value in (video, audio) if value))
    if errors:
        return "error", "Destino precisa de atenção", " • ".join(errors)
    parent = path.parent
    if not parent.exists():
        return "warning", "Pasta ainda não existe", "O CinePulse tentará usar o ancestral existente, mas é mais seguro escolher uma pasta já criada."
    return "ok", "Destino pronto", f"{path.suffix.upper().lstrip('.') or 'MP4'} • {parent}"


def target_ratio(aspect: str, source_width: int, source_height: int) -> float:
    if aspect.startswith("9:16"):
        return 9 / 16
    if aspect.startswith("IMAX"):
        return 1.90
    if aspect.startswith("Cinema Wide"):
        return 2.39
    if aspect.startswith("Original") and source_width > 0 and source_height > 0:
        return source_width / source_height
    return 16 / 9


def framing_retention(source_width: int, source_height: int, ratio: float, cover: bool) -> float:
    if source_width <= 0 or source_height <= 0 or ratio <= 0 or not cover:
        return 1.0
    source_ratio = source_width / source_height
    if source_ratio > ratio:
        return max(0.0, min(1.0, ratio / source_ratio))
    return max(0.0, min(1.0, source_ratio / ratio))


def framing_explanation(source_width: int, source_height: int, aspect: str, fit_mode: str) -> str:
    ratio = target_ratio(aspect, source_width, source_height)
    cover = fit_mode.startswith("Preencher")
    if aspect.startswith("Original"):
        return "Formato original • nenhuma mudança de proporção; o enquadramento permanece fiel à fonte."
    if cover:
        kept = framing_retention(source_width, source_height, ratio, True) * 100
        cropped = max(0.0, 100.0 - kept)
        if cropped < 0.5:
            return "Preencher • a proporção já combina com o destino; praticamente não há corte."
        return f"Preencher • ocupa toda a tela e corta aproximadamente {cropped:.0f}% da área da fonte nas bordas."
    return "Encaixar • preserva 100% do quadro e adiciona barras quando a proporção da fonte não coincide."


def _fit_source(source: np.ndarray, width: int, height: int, *, cover: bool) -> np.ndarray:
    src_h, src_w = source.shape[:2]
    if cover:
        src_ratio = src_w / max(1, src_h)
        target = width / max(1, height)
        if src_ratio > target:
            crop_w = max(1, round(src_h * target))
            start = max(0, (src_w - crop_w) // 2)
            cropped = source[:, start : start + crop_w]
        else:
            crop_h = max(1, round(src_w / target))
            start = max(0, (src_h - crop_h) // 2)
            cropped = source[start : start + crop_h, :]
        return resize_nearest(cropped, width, height)

    scale = min(width / max(1, src_w), height / max(1, src_h))
    inner_w = max(1, min(width, round(src_w * scale)))
    inner_h = max(1, min(height, round(src_h * scale)))
    resized = resize_nearest(source, inner_w, inner_h)
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:] = np.asarray((8, 11, 18), dtype=np.uint8)
    x = (width - inner_w) // 2
    y = (height - inner_h) // 2
    frame[y : y + inner_h, x : x + inner_w] = resized
    return frame


def framing_preview(
    source: np.ndarray,
    aspect: str,
    fit_mode: str,
    *,
    source_width: int | None = None,
    source_height: int | None = None,
    canvas_width: int = 640,
    canvas_height: int = 360,
) -> np.ndarray:
    """Visualize cover/contain geometry on a neutral cinema canvas.

    The image manipulation follows the same center crop vs. letterbox semantics
    as ``VideoOptimizerStudio._scale_filter``.  A thin bright frame is a UI
    guide only and is not part of the exported video.
    """
    src_h, src_w = source.shape[:2]
    logical_w = int(source_width or src_w)
    logical_h = int(source_height or src_h)
    ratio = target_ratio(aspect, logical_w, logical_h)

    margin = 14
    available_w = max(32, canvas_width - margin * 2)
    available_h = max(18, canvas_height - margin * 2)
    if available_w / available_h > ratio:
        out_h = available_h
        out_w = max(2, round(out_h * ratio))
    else:
        out_w = available_w
        out_h = max(2, round(out_w / ratio))

    fitted = _fit_source(source, out_w, out_h, cover=fit_mode.startswith("Preencher"))
    canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    canvas[:] = np.asarray((8, 11, 18), dtype=np.uint8)
    x = (canvas_width - out_w) // 2
    y = (canvas_height - out_h) // 2
    canvas[y : y + out_h, x : x + out_w] = fitted

    # UI-only framing guide; cyan uses the existing CinePulse brand token.
    guide = np.asarray((66, 216, 255), dtype=np.uint8)
    x2 = min(canvas_width - 1, x + out_w - 1)
    y2 = min(canvas_height - 1, y + out_h - 1)
    canvas[y : min(y + 2, canvas_height), x : x2 + 1] = guide
    canvas[max(y2 - 1, 0) : y2 + 1, x : x2 + 1] = guide
    canvas[y : y2 + 1, x : min(x + 2, canvas_width)] = guide
    canvas[y : y2 + 1, max(x2 - 1, 0) : x2 + 1] = guide
    return canvas
