from __future__ import annotations

import math
from dataclasses import dataclass

from .overlay_composer import OverlayLayer, OverlayScene, OverlaySceneError, VisualizerSpec


@dataclass(frozen=True)
class AssetInputPlan:
    layer_id: str
    input_index: int
    args: tuple[str, ...]


@dataclass(frozen=True)
class OverlayFfmpegPlan:
    asset_inputs: tuple[AssetInputPlan, ...]
    filter_complex: str
    output_label: str

    @property
    def input_args(self) -> tuple[str, ...]:
        return tuple(arg for item in self.asset_inputs for arg in item.args)


class OverlayFfmpegError(OverlaySceneError):
    pass


def _label(value: str) -> str:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return value
    return f"[{value}]"


def _ff(value: float, digits: int = 6) -> str:
    if not math.isfinite(float(value)):
        raise OverlayFfmpegError("Valor numérico inválido no plano FFmpeg.")
    text = f"{float(value):.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


def _color_coefficients(color: str) -> tuple[str, str, str]:
    value = color.strip().lstrip("#")
    try:
        red, green, blue = (int(value[index : index + 2], 16) / 255.0 for index in (0, 2, 4))
    except (ValueError, TypeError) as exc:
        raise OverlayFfmpegError("Cor inválida para visualizador.") from exc
    return _ff(red, 4), _ff(green, 4), _ff(blue, 4)


def _asset_input(layer: OverlayLayer, input_index: int, fps: float) -> AssetInputPlan:
    assert layer.asset is not None
    if layer.asset.media_kind == "png":
        args = ("-loop", "1", "-framerate", _ff(fps, 3), "-i", layer.asset.path)
    elif layer.asset.media_kind == "gif":
        # The GIF demuxer is looped at the stream level. The final overlay follows
        # the base video duration, so no giant expanded cache is created.
        args = ("-stream_loop", "-1", "-i", layer.asset.path)
    else:
        raise OverlayFfmpegError(f"Asset não suportado: {layer.asset.media_kind}")
    return AssetInputPlan(layer.id, int(input_index), args)


def _asset_filter(layer: OverlayLayer, input_index: int, width: int, height: int, label: str) -> str:
    assert layer.asset is not None
    transform = layer.transform
    filters: list[str] = []
    if abs(layer.asset.speed - 1.0) > 1e-6:
        filters.append(f"setpts=PTS/{_ff(layer.asset.speed)}")
    if transform.preserve_aspect:
        filters.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos")
        filters.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black@0")
    else:
        filters.append(f"scale={width}:{height}:flags=lanczos")
    filters.append("format=rgba")
    if abs(transform.rotation_deg) > 1e-6:
        filters.append(f"rotate={_ff(transform.rotation_deg)}*PI/180:ow=iw:oh=ih:c=none")
    if transform.opacity < 0.999999:
        filters.append(f"colorchannelmixer=aa={_ff(transform.opacity)}")
    return f"[{input_index}:v]{','.join(filters)}[{label}]"


def _audio_focus_filters(spec: VisualizerSpec) -> list[str]:
    filters: list[str] = []
    if spec.focus == "bass":
        filters.append("lowpass=f=280")
    elif spec.focus == "mids":
        filters.extend(("highpass=f=220", "lowpass=f=4200"))
    elif spec.focus == "highs":
        filters.append("highpass=f=3800")
    elif spec.focus == "beats":
        filters.extend(("highpass=f=55", "lowpass=f=220"))
    if abs(spec.sensitivity - 1.0) > 1e-6:
        filters.append(f"volume={_ff(spec.sensitivity)}")
    return filters


def _visualizer_filter(
    audio_source: str,
    layer: OverlayLayer,
    width: int,
    height: int,
    fps: float,
    label: str,
) -> str:
    assert layer.visualizer is not None
    spec = layer.visualizer
    filters = _audio_focus_filters(spec)
    if spec.style == "waveform":
        filters.append(f"showwaves=s={width}x{height}:mode=line:rate={_ff(fps, 3)}:colors=white")
    elif spec.style == "bars":
        filters.append(f"showfreqs=s={width}x{height}:mode=bar:ascale=log:fscale=log:colors=white")
    elif spec.style == "spectrum":
        # A frequency curve gives the creator a clean, recolorable spectrum on a
        # transparent background and is cheaper than a scrolling spectrogram.
        filters.append(f"showfreqs=s={width}x{height}:mode=line:ascale=log:fscale=log:colors=white")
    else:
        raise OverlayFfmpegError(f"Visualizador não suportado: {spec.style}")
    red, green, blue = _color_coefficients(spec.color)
    filters.extend(
        (
            "format=rgba",
            "colorkey=0x000000:0.05:0.0",
            f"colorchannelmixer=rr={red}:gg={green}:bb={blue}",
        )
    )
    return f"{_label(audio_source)}{','.join(filters)}[{label}]"


def build_overlay_ffmpeg_plan(
    scene: OverlayScene,
    *,
    canvas_width: int,
    canvas_height: int,
    fps: float,
    first_asset_input_index: int,
    base_video_label: str,
    audio_label: str | None,
) -> OverlayFfmpegPlan:
    """Build deterministic extra inputs and a filter-complex fragment.

    The caller owns the base video/audio graph. This function only appends the
    composition fragment and returns the final video label. Assets are streamed
    and looped; GIF frames are never expanded to hours of temporary images.
    """
    scene.validate()
    if canvas_width <= 0 or canvas_height <= 0 or fps <= 0:
        raise OverlayFfmpegError("Canvas/FPS inválidos para Overlay Composer.")
    active = scene.active_layers
    asset_layers = [layer for layer in active if layer.kind == "asset"]
    visualizer_layers = [layer for layer in active if layer.kind == "visualizer"]
    if visualizer_layers and not audio_label:
        raise OverlayFfmpegError("Visualizador ativo exige uma faixa de áudio.")

    asset_inputs = tuple(
        _asset_input(layer, first_asset_input_index + index, fps)
        for index, layer in enumerate(asset_layers)
    )
    index_by_id = {item.layer_id: item.input_index for item in asset_inputs}

    filters: list[str] = []
    audio_sources: dict[str, str] = {}
    if visualizer_layers:
        assert audio_label is not None
        if len(visualizer_layers) == 1:
            audio_sources[visualizer_layers[0].id] = audio_label
        else:
            split_labels = [f"ov_audio_{index}" for index in range(len(visualizer_layers))]
            outputs = "".join(f"[{label}]" for label in split_labels)
            filters.append(f"{_label(audio_label)}asplit={len(split_labels)}{outputs}")
            for layer, label in zip(visualizer_layers, split_labels):
                audio_sources[layer.id] = label

    prepared_labels: dict[str, str] = {}
    for index, layer in enumerate(active):
        _x, _y, width, height = layer.transform.rect.pixels(canvas_width, canvas_height)
        label = f"ov_src_{index}"
        if layer.kind == "asset":
            filters.append(_asset_filter(layer, index_by_id[layer.id], width, height, label))
        else:
            filters.append(_visualizer_filter(audio_sources[layer.id], layer, width, height, fps, label))
        prepared_labels[layer.id] = label

    current = base_video_label.strip("[]")
    for index, layer in enumerate(active):
        x, y, _width, _height = layer.transform.rect.pixels(canvas_width, canvas_height)
        output = f"ov_mix_{index}"
        filters.append(
            f"[{current}][{prepared_labels[layer.id]}]overlay=x={x}:y={y}:eof_action=pass:shortest=0:format=auto[{output}]"
        )
        current = output

    return OverlayFfmpegPlan(asset_inputs, ";".join(filters), current)
