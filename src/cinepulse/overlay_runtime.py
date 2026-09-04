from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .overlay_composer import OverlayScene, OverlaySceneError


@dataclass(frozen=True)
class OverlayValidation:
    scene: OverlayScene
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def scene_from_json(payload: str | None) -> OverlayScene:
    text = (payload or "").strip()
    if not text:
        return OverlayScene()
    return OverlayScene.from_json(text)


def scene_to_json(scene: OverlayScene | None) -> str:
    return (scene or OverlayScene()).to_json()


def has_visualizer(scene: OverlayScene) -> bool:
    return any(layer.enabled and layer.kind == "visualizer" for layer in scene.layers)


def has_assets(scene: OverlayScene) -> bool:
    return any(layer.enabled and layer.kind == "asset" for layer in scene.layers)


def validate_scene_sources(scene: OverlayScene, *, audio_available: bool) -> OverlayValidation:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        scene.validate()
    except OverlaySceneError as exc:
        return OverlayValidation(scene, (str(exc),), ())

    for layer in scene.active_layers:
        if layer.asset is not None:
            path = Path(layer.asset.path).expanduser()
            if not path.is_file():
                errors.append(f"Overlay ‘{layer.name}’: arquivo não encontrado: {layer.asset.path}")
            elif path.suffix.lower() not in {".png", ".gif"}:
                errors.append(f"Overlay ‘{layer.name}’: somente PNG/GIF são aceitos nesta versão Preview.")
        if layer.visualizer is not None and not audio_available:
            errors.append(f"Visualizador ‘{layer.name}’ exige uma faixa de áudio válida.")

    if len(scene.active_layers) > 12:
        warnings.append("Mais de 12 overlays ativos podem aumentar bastante o custo da composição final.")
    gif_count = sum(1 for layer in scene.active_layers if layer.asset and layer.asset.media_kind == "gif")
    if gif_count > 4:
        warnings.append("Muitos GIFs simultâneos podem elevar uso de CPU durante a codificação final.")
    return OverlayValidation(scene, tuple(errors), tuple(warnings))


def summary(scene: OverlayScene) -> str:
    assets = sum(1 for layer in scene.active_layers if layer.kind == "asset")
    visualizers = sum(1 for layer in scene.active_layers if layer.kind == "visualizer")
    if not assets and not visualizers:
        return "sem overlays"
    parts: list[str] = []
    if assets:
        parts.append(f"{assets} PNG/GIF")
    if visualizers:
        parts.append(f"{visualizers} gráfico(s) musical(is)")
    groups = len(scene.groups)
    if groups:
        parts.append(f"{groups} grupo(s)")
    return " • ".join(parts)
