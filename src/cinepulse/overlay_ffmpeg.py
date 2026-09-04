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


def _ffmpeg_color(color: str) -> str:
    value = color.strip().lstrip("#")
    if len(value) != 6:
        raise OverlayFfmpegError("Cor inválida para visualizador.")
    try:
        int(value, 16)
    except ValueError as exc:
        raise OverlayFfmpegError("Cor inválida para visualizador.") from exc
    return "0x" + value.upper()


def _asset_input(layer: OverlayLayer, input_index: int, fps: float) -> AssetInputPlan:
    assert layer.asset is not None
    if layer.asset.media_kind == "png":
        args = ("-loop", "1", "-framerate", _ff(fps, 3), "-i", layer.asset.path)
    elif layer.asset.media_kind == "gif":
        args = (("-stream_loop", "-1") if layer.asset.loop else ()) + ("-i", layer.asset.path)
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


def _thickness_filters(spec: VisualizerSpec, *, line_style: bool) -> list[str]:
    if not line_style:
        return []
    # showwaves/showfreqs do not expose line thickness directly. Repeating the
    # official 3x3 dilation filter expands the opaque line deterministically.
    # The normalized model range 0.02..1 maps to zero..three passes.
    passes = max(0, min(3, int(round(float(spec.thickness) * 3.0))))
    return ["dilation"] * passes


def _visualizer_filters(
    audio_source: str,
    layer: OverlayLayer,
    width: int,
    height: int,
    fps: float,
    label: str,
) -> tuple[str, ...]:
    assert layer.visualizer is not None
    spec = layer.visualizer
    primary = _ffmpeg_color(spec.color)
    secondary = _ffmpeg_color(spec.secondary_color)
    source_filters = _audio_focus_filters(spec)

    if spec.style == "waveform":
        source_filters.append(
            f"showwaves=s={width}x{height}:mode=line:rate={_ff(fps, 3)}:colors={primary}"
        )
        source_filters.extend(_thickness_filters(spec, line_style=True))
        source_filters.extend(
            (
                "format=rgba",
                "colorkey=0x000000:0.05:0.0",
                f"colorchannelmixer=aa={_ff(layer.transform.opacity)}",
            )
        )
        return (f"{_label(audio_source)}{','.join(source_filters)}[{label}]",)

    if spec.style not in {"bars", "spectrum"}:
        raise OverlayFfmpegError(f"Visualizador não suportado: {spec.style}")

    mirrored = bool(spec.mirror)
    generated_height = max(2, math.ceil(height / 2)) if mirrored else height
    generated_width = width
    if spec.style == "bars":
        generated_width = max(4, min(int(spec.bars), width))
        mode = "bar"
    else:
        mode = "line"

    source_filters.append(
        f"showfreqs=s={generated_width}x{generated_height}:mode={mode}:ascale=log:fscale=log:"
        f"colors={primary}|{secondary}:cmode=combined"
    )
    if generated_width != width:
        # Pixel-preserving enlargement turns the chosen spectral bins into the
        # exact creator-facing bar count instead of thousands of 1px FFT bins.
        source_filters.append(f"scale={width}:{generated_height}:flags=neighbor")
    source_filters.extend(_thickness_filters(spec, line_style=spec.style == "spectrum"))
    source_filters.extend(
        (
            "format=rgba",
            "colorkey=0x000000:0.05:0.0",
            f"colorchannelmixer=aa={_ff(layer.transform.opacity)}",
        )
    )

    if not mirrored:
        return (f"{_label(audio_source)}{','.join(source_filters)}[{label}]",)

    half = f"{label}_half"
    top_raw = f"{label}_top_raw"
    bottom = f"{label}_bottom"
    top = f"{label}_top"
    return (
        f"{_label(audio_source)}{','.join(source_filters)}[{half}]",
        f"[{half}]split=2[{top_raw}][{bottom}]",
        f"[{top_raw}]vflip[{top}]",
        f"[{top}][{bottom}]vstack=inputs=2,scale={width}:{height}:flags=neighbor[{label}]",
    )


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
            for layer, split_label in zip(visualizer_layers, split_labels):
                audio_sources[layer.id] = split_label

    prepared_labels: dict[str, str] = {}
    for index, layer in enumerate(active):
        _x, _y, width, height = layer.transform.rect.pixels(canvas_width, canvas_height)
        label = f"ov_src_{index}"
        if layer.kind == "asset":
            filters.append(_asset_filter(layer, index_by_id[layer.id], width, height, label))
        else:
            filters.extend(_visualizer_filters(audio_sources[layer.id], layer, width, height, fps, label))
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
