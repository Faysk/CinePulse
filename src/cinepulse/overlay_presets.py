from __future__ import annotations

from dataclasses import dataclass, replace

from .overlay_composer import (
    LayerTransform,
    NormalizedRect,
    OverlayGroup,
    OverlayLayer,
    OverlayScene,
    OverlaySceneError,
    VisualizerSpec,
    new_layer_id,
)


@dataclass(frozen=True)
class OverlayLayoutPreset:
    key: str
    label: str
    description: str
    asset_rect: NormalizedRect | None
    visualizer_rect: NormalizedRect
    visualizer_style: str
    visualizer_focus: str = "bass"
    visualizer_color: str = "#F2E5C9"
    group_pair: bool = True
    safe_area_profile: str = "frame"


LAYOUT_PRESETS: tuple[OverlayLayoutPreset, ...] = (
    OverlayLayoutPreset(
        key="character-wave-right",
        label="Personagem + Waveform",
        description="Personagem no canto direito com waveform horizontal acompanhando a base.",
        asset_rect=NormalizedRect(0.72, 0.48, 0.22, 0.40),
        visualizer_rect=NormalizedRect(0.53, 0.84, 0.40, 0.075),
        visualizer_style="waveform",
        visualizer_focus="bass",
    ),
    OverlayLayoutPreset(
        key="character-bars-right",
        label="Personagem + Barras",
        description="Personagem à direita com barras musicais compactas na região inferior.",
        asset_rect=NormalizedRect(0.70, 0.44, 0.24, 0.44),
        visualizer_rect=NormalizedRect(0.58, 0.76, 0.34, 0.14),
        visualizer_style="bars",
        visualizer_focus="beats",
    ),
    OverlayLayoutPreset(
        key="wide-wave-bottom",
        label="Waveform panorâmico",
        description="Waveform largo junto à base; mantém o personagem menor no canto quando disponível.",
        asset_rect=NormalizedRect(0.75, 0.53, 0.18, 0.34),
        visualizer_rect=NormalizedRect(0.08, 0.86, 0.84, 0.055),
        visualizer_style="waveform",
        visualizer_focus="full",
        group_pair=False,
    ),
    OverlayLayoutPreset(
        key="minimal-spectrum",
        label="Espectro minimalista",
        description="Espectro central e discreto para vídeos atmosféricos e Lo-fi.",
        asset_rect=NormalizedRect(0.76, 0.55, 0.16, 0.30),
        visualizer_rect=NormalizedRect(0.20, 0.82, 0.60, 0.075),
        visualizer_style="spectrum",
        visualizer_focus="full",
        group_pair=False,
    ),
)

PRESET_BY_KEY = {preset.key: preset for preset in LAYOUT_PRESETS}


def preset(key: str) -> OverlayLayoutPreset:
    try:
        return PRESET_BY_KEY[key]
    except KeyError as exc:
        raise OverlaySceneError(f"Preset de composição desconhecido: {key}") from exc


def _first_layer(scene: OverlayScene, kind: str, explicit_id: str | None) -> OverlayLayer | None:
    if explicit_id:
        layer = scene.layer(explicit_id)
        if layer.kind != kind:
            raise OverlaySceneError(f"Layer {explicit_id} não é do tipo {kind}.")
        return layer
    return next((layer for layer in scene.ordered_layers if layer.kind == kind), None)


def _replace_rect(layer: OverlayLayer, rect: NormalizedRect) -> OverlayLayer:
    transform = replace(layer.transform, rect=rect)
    return replace(layer, transform=transform)


def _replace_visualizer(layer: OverlayLayer, layout: OverlayLayoutPreset) -> OverlayLayer:
    if layer.visualizer is None:
        raise OverlaySceneError("Preset musical exige uma layer visualizer.")
    visualizer = replace(
        layer.visualizer,
        style=layout.visualizer_style,
        focus=layout.visualizer_focus,
        color=layout.visualizer_color,
    )
    return replace(_replace_rect(layer, layout.visualizer_rect), visualizer=visualizer)


def _remove_groups_touching(scene: OverlayScene, member_ids: set[str]) -> OverlayScene:
    groups = tuple(group for group in scene.groups if member_ids.isdisjoint(group.member_ids))
    result = OverlayScene(scene.layers, groups, scene.schema, scene.safe_area_profile)
    result.validate()
    return result


def apply_layout_preset(
    scene: OverlayScene,
    key: str,
    *,
    asset_layer_id: str | None = None,
    visualizer_layer_id: str | None = None,
) -> OverlayScene:
    """Apply a creator-friendly layout without changing asset files.

    A visualizer is required because every built-in recipe is music-oriented.
    The asset is optional so creators can use a pure waveform/spectrum preset.
    Existing groups touching the chosen pair are removed before a new pair group
    is created; unrelated groups remain untouched.
    """
    scene.validate()
    layout = preset(key)
    asset = _first_layer(scene, "asset", asset_layer_id)
    visualizer = _first_layer(scene, "visualizer", visualizer_layer_id)
    if visualizer is None:
        raise OverlaySceneError("Adicione um Waveform/Barras/Espectro antes de aplicar este layout.")

    result = scene.replace_layer(_replace_visualizer(visualizer, layout))
    if asset is not None and layout.asset_rect is not None:
        result = result.replace_layer(_replace_rect(asset, layout.asset_rect))

    selected_ids = {visualizer.id}
    if asset is not None:
        selected_ids.add(asset.id)
    result = _remove_groups_touching(result, selected_ids)

    if layout.group_pair and asset is not None:
        group = OverlayGroup(
            new_layer_id("group"),
            layout.label,
            (asset.id, visualizer.id),
        )
        result = result.add_group(group)

    result = OverlayScene(result.layers, result.groups, result.schema, layout.safe_area_profile)
    result.validate()
    return result


def preset_summary(key: str) -> str:
    layout = preset(key)
    return f"{layout.label} — {layout.description}"
