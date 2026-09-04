from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "cinepulse.overlay-scene/1"
LAYER_KINDS = frozenset({"asset", "visualizer"})
ASSET_KINDS = frozenset({"png", "gif"})
VISUALIZER_STYLES = frozenset({"waveform", "bars", "spectrum"})
VISUALIZER_FOCUS = frozenset({"full", "bass", "mids", "highs", "beats"})


class OverlaySceneError(ValueError):
    """Raised when an overlay scene violates a deterministic composition contract."""


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise OverlaySceneError(f"{name} precisa ser finito.")
    return value


def new_layer_id(prefix: str = "layer") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class NormalizedRect:
    """Canvas-relative rectangle.

    ``x``/``y`` are the top-left position and ``width``/``height`` are relative
    to the final canvas. Coordinates may be slightly outside the canvas so a
    creator can intentionally crop an overlay at an edge.
    """

    x: float = 0.70
    y: float = 0.68
    width: float = 0.25
    height: float = 0.25

    def validate(self) -> None:
        x = _finite(self.x, "x")
        y = _finite(self.y, "y")
        width = _finite(self.width, "width")
        height = _finite(self.height, "height")
        if not (-2.0 <= x <= 2.0 and -2.0 <= y <= 2.0):
            raise OverlaySceneError("x/y precisam ficar entre -2 e 2 do canvas.")
        if not (0.001 <= width <= 4.0 and 0.001 <= height <= 4.0):
            raise OverlaySceneError("width/height precisam ficar entre 0.001 e 4 do canvas.")

    def pixels(self, canvas_width: int, canvas_height: int) -> tuple[int, int, int, int]:
        self.validate()
        if canvas_width <= 0 or canvas_height <= 0:
            raise OverlaySceneError("Canvas precisa ter dimensões positivas.")
        x = int(round(self.x * canvas_width))
        y = int(round(self.y * canvas_height))
        width = max(1, int(round(self.width * canvas_width)))
        height = max(1, int(round(self.height * canvas_height)))
        return x, y, width, height

    def moved(self, dx: float, dy: float) -> "NormalizedRect":
        return NormalizedRect(self.x + float(dx), self.y + float(dy), self.width, self.height)

    def scaled_about(self, factor: float, origin_x: float, origin_y: float) -> "NormalizedRect":
        factor = _finite(factor, "factor")
        if factor <= 0:
            raise OverlaySceneError("Escala precisa ser positiva.")
        return NormalizedRect(
            origin_x + (self.x - origin_x) * factor,
            origin_y + (self.y - origin_y) * factor,
            self.width * factor,
            self.height * factor,
        )


@dataclass(frozen=True)
class LayerTransform:
    rect: NormalizedRect = field(default_factory=NormalizedRect)
    opacity: float = 1.0
    rotation_deg: float = 0.0
    preserve_aspect: bool = True

    def validate(self) -> None:
        self.rect.validate()
        opacity = _finite(self.opacity, "opacity")
        rotation = _finite(self.rotation_deg, "rotation_deg")
        if not 0.0 <= opacity <= 1.0:
            raise OverlaySceneError("opacity precisa ficar entre 0 e 1.")
        if not -3600.0 <= rotation <= 3600.0:
            raise OverlaySceneError("rotation_deg fora do limite de segurança.")


@dataclass(frozen=True)
class AssetSpec:
    path: str
    media_kind: str
    loop: bool = True
    speed: float = 1.0

    def validate(self) -> None:
        if self.media_kind not in ASSET_KINDS:
            raise OverlaySceneError(f"Asset não suportado: {self.media_kind}")
        if not self.path.strip():
            raise OverlaySceneError("Asset precisa apontar para um arquivo.")
        speed = _finite(self.speed, "asset.speed")
        if not 0.05 <= speed <= 8.0:
            raise OverlaySceneError("Velocidade do asset precisa ficar entre 0.05x e 8x.")
        suffix = Path(self.path).suffix.lower()
        expected = {"png": ".png", "gif": ".gif"}[self.media_kind]
        if suffix and suffix != expected:
            raise OverlaySceneError(f"Asset {self.media_kind} precisa usar extensão {expected}.")


@dataclass(frozen=True)
class VisualizerSpec:
    style: str = "waveform"
    color: str = "#FFFFFF"
    secondary_color: str = "#42D8FF"
    sensitivity: float = 1.0
    smoothing: float = 0.82
    thickness: float = 0.42
    bars: int = 64
    mirror: bool = False
    focus: str = "full"

    def validate(self) -> None:
        if self.style not in VISUALIZER_STYLES:
            raise OverlaySceneError(f"Visualizador não suportado: {self.style}")
        if self.focus not in VISUALIZER_FOCUS:
            raise OverlaySceneError(f"Foco de áudio não suportado: {self.focus}")
        for name, value, low, high in (
            ("sensitivity", self.sensitivity, 0.05, 8.0),
            ("smoothing", self.smoothing, 0.0, 1.0),
            ("thickness", self.thickness, 0.02, 1.0),
        ):
            current = _finite(value, name)
            if not low <= current <= high:
                raise OverlaySceneError(f"{name} precisa ficar entre {low} e {high}.")
        if not 4 <= int(self.bars) <= 512:
            raise OverlaySceneError("bars precisa ficar entre 4 e 512.")
        for value in (self.color, self.secondary_color):
            if len(value) != 7 or not value.startswith("#"):
                raise OverlaySceneError("Cores precisam usar #RRGGBB.")
            try:
                int(value[1:], 16)
            except ValueError as exc:
                raise OverlaySceneError("Cores precisam usar #RRGGBB.") from exc


@dataclass(frozen=True)
class OverlayLayer:
    id: str
    name: str
    kind: str
    z_index: int = 0
    enabled: bool = True
    locked: bool = False
    transform: LayerTransform = field(default_factory=LayerTransform)
    asset: AssetSpec | None = None
    visualizer: VisualizerSpec | None = None

    def validate(self) -> None:
        if not self.id.strip():
            raise OverlaySceneError("Layer precisa de id.")
        if not self.name.strip():
            raise OverlaySceneError("Layer precisa de nome.")
        if self.kind not in LAYER_KINDS:
            raise OverlaySceneError(f"Tipo de layer desconhecido: {self.kind}")
        self.transform.validate()
        if self.kind == "asset":
            if self.asset is None or self.visualizer is not None:
                raise OverlaySceneError("Layer asset precisa somente de AssetSpec.")
            self.asset.validate()
        elif self.kind == "visualizer":
            if self.visualizer is None or self.asset is not None:
                raise OverlaySceneError("Layer visualizer precisa somente de VisualizerSpec.")
            self.visualizer.validate()


@dataclass(frozen=True)
class OverlayGroup:
    id: str
    name: str
    member_ids: tuple[str, ...]

    def validate(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise OverlaySceneError("Grupo precisa de id e nome.")
        if len(self.member_ids) < 2:
            raise OverlaySceneError("Grupo precisa ter pelo menos duas layers.")
        if len(set(self.member_ids)) != len(self.member_ids):
            raise OverlaySceneError("Grupo não pode repetir a mesma layer.")


@dataclass(frozen=True)
class OverlayScene:
    layers: tuple[OverlayLayer, ...] = ()
    groups: tuple[OverlayGroup, ...] = ()
    schema: str = SCHEMA
    safe_area_profile: str = "none"

    def validate(self) -> None:
        if self.schema != SCHEMA:
            raise OverlaySceneError(f"Schema de overlay não suportado: {self.schema}")
        ids: set[str] = set()
        for layer in self.layers:
            layer.validate()
            if layer.id in ids:
                raise OverlaySceneError(f"Layer duplicada: {layer.id}")
            ids.add(layer.id)
        group_ids: set[str] = set()
        grouped_layers: set[str] = set()
        for group in self.groups:
            group.validate()
            if group.id in group_ids:
                raise OverlaySceneError(f"Grupo duplicado: {group.id}")
            group_ids.add(group.id)
            missing = set(group.member_ids) - ids
            if missing:
                raise OverlaySceneError(f"Grupo referencia layers inexistentes: {sorted(missing)}")
            overlap = grouped_layers.intersection(group.member_ids)
            if overlap:
                raise OverlaySceneError(f"Layer pertence a mais de um grupo: {sorted(overlap)}")
            grouped_layers.update(group.member_ids)

    @property
    def ordered_layers(self) -> tuple[OverlayLayer, ...]:
        return tuple(sorted(self.layers, key=lambda layer: (layer.z_index, layer.id)))

    @property
    def active_layers(self) -> tuple[OverlayLayer, ...]:
        return tuple(layer for layer in self.ordered_layers if layer.enabled)

    def layer(self, layer_id: str) -> OverlayLayer:
        for layer in self.layers:
            if layer.id == layer_id:
                return layer
        raise OverlaySceneError(f"Layer não encontrada: {layer_id}")

    def group(self, group_id: str) -> OverlayGroup:
        for group in self.groups:
            if group.id == group_id:
                return group
        raise OverlaySceneError(f"Grupo não encontrado: {group_id}")

    def replace_layer(self, replacement: OverlayLayer) -> "OverlayScene":
        replacement.validate()
        found = False
        layers: list[OverlayLayer] = []
        for layer in self.layers:
            if layer.id == replacement.id:
                layers.append(replacement)
                found = True
            else:
                layers.append(layer)
        if not found:
            raise OverlaySceneError(f"Layer não encontrada: {replacement.id}")
        scene = OverlayScene(tuple(layers), self.groups, self.schema, self.safe_area_profile)
        scene.validate()
        return scene

    def add_layer(self, layer: OverlayLayer) -> "OverlayScene":
        if any(existing.id == layer.id for existing in self.layers):
            raise OverlaySceneError(f"Layer já existe: {layer.id}")
        scene = OverlayScene(self.layers + (layer,), self.groups, self.schema, self.safe_area_profile)
        scene.validate()
        return scene

    def remove_layer(self, layer_id: str) -> "OverlayScene":
        if not any(layer.id == layer_id for layer in self.layers):
            return self
        layers = tuple(layer for layer in self.layers if layer.id != layer_id)
        groups: list[OverlayGroup] = []
        for group in self.groups:
            members = tuple(member for member in group.member_ids if member != layer_id)
            if len(members) >= 2:
                groups.append(OverlayGroup(group.id, group.name, members))
        scene = OverlayScene(layers, tuple(groups), self.schema, self.safe_area_profile)
        scene.validate()
        return scene

    def add_group(self, group: OverlayGroup) -> "OverlayScene":
        scene = OverlayScene(self.layers, self.groups + (group,), self.schema, self.safe_area_profile)
        scene.validate()
        return scene

    def remove_group(self, group_id: str) -> "OverlayScene":
        scene = OverlayScene(self.layers, tuple(group for group in self.groups if group.id != group_id), self.schema, self.safe_area_profile)
        scene.validate()
        return scene

    def group_bounds(self, group_id: str) -> NormalizedRect:
        group = self.group(group_id)
        rects = [self.layer(member).transform.rect for member in group.member_ids]
        left = min(rect.x for rect in rects)
        top = min(rect.y for rect in rects)
        right = max(rect.x + rect.width for rect in rects)
        bottom = max(rect.y + rect.height for rect in rects)
        return NormalizedRect(left, top, right - left, bottom - top)

    def move_group(self, group_id: str, dx: float, dy: float) -> "OverlayScene":
        group = self.group(group_id)
        members = set(group.member_ids)
        layers: list[OverlayLayer] = []
        for layer in self.layers:
            if layer.id not in members or layer.locked:
                layers.append(layer)
                continue
            transform = LayerTransform(
                rect=layer.transform.rect.moved(dx, dy),
                opacity=layer.transform.opacity,
                rotation_deg=layer.transform.rotation_deg,
                preserve_aspect=layer.transform.preserve_aspect,
            )
            layers.append(_replace_transform(layer, transform))
        scene = OverlayScene(tuple(layers), self.groups, self.schema, self.safe_area_profile)
        scene.validate()
        return scene

    def scale_group(self, group_id: str, factor: float) -> "OverlayScene":
        bounds = self.group_bounds(group_id)
        origin_x = bounds.x + bounds.width / 2.0
        origin_y = bounds.y + bounds.height / 2.0
        group = self.group(group_id)
        members = set(group.member_ids)
        layers: list[OverlayLayer] = []
        for layer in self.layers:
            if layer.id not in members or layer.locked:
                layers.append(layer)
                continue
            transform = LayerTransform(
                rect=layer.transform.rect.scaled_about(factor, origin_x, origin_y),
                opacity=layer.transform.opacity,
                rotation_deg=layer.transform.rotation_deg,
                preserve_aspect=layer.transform.preserve_aspect,
            )
            layers.append(_replace_transform(layer, transform))
        scene = OverlayScene(tuple(layers), self.groups, self.schema, self.safe_area_profile)
        scene.validate()
        return scene

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema": self.schema,
            "safe_area_profile": self.safe_area_profile,
            "layers": [asdict(layer) for layer in self.layers],
            "groups": [asdict(group) for group in self.groups],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OverlayScene":
        if payload.get("schema") != SCHEMA:
            raise OverlaySceneError(f"Schema de overlay não suportado: {payload.get('schema')}")
        layers: list[OverlayLayer] = []
        for raw in payload.get("layers", []):
            transform_raw = raw.get("transform", {})
            rect_raw = transform_raw.get("rect", {})
            transform = LayerTransform(
                rect=NormalizedRect(**rect_raw),
                opacity=transform_raw.get("opacity", 1.0),
                rotation_deg=transform_raw.get("rotation_deg", 0.0),
                preserve_aspect=transform_raw.get("preserve_aspect", True),
            )
            asset_raw = raw.get("asset")
            visualizer_raw = raw.get("visualizer")
            layers.append(
                OverlayLayer(
                    id=str(raw["id"]),
                    name=str(raw["name"]),
                    kind=str(raw["kind"]),
                    z_index=int(raw.get("z_index", 0)),
                    enabled=bool(raw.get("enabled", True)),
                    locked=bool(raw.get("locked", False)),
                    transform=transform,
                    asset=AssetSpec(**asset_raw) if asset_raw else None,
                    visualizer=VisualizerSpec(**visualizer_raw) if visualizer_raw else None,
                )
            )
        groups = tuple(
            OverlayGroup(str(raw["id"]), str(raw["name"]), tuple(str(item) for item in raw.get("member_ids", ())))
            for raw in payload.get("groups", [])
        )
        scene = cls(tuple(layers), groups, str(payload["schema"]), str(payload.get("safe_area_profile", "none")))
        scene.validate()
        return scene

    @classmethod
    def from_json(cls, payload: str) -> "OverlayScene":
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise OverlaySceneError("JSON de overlay inválido.") from exc
        if not isinstance(raw, dict):
            raise OverlaySceneError("Cena de overlay precisa ser um objeto JSON.")
        return cls.from_dict(raw)


def _replace_transform(layer: OverlayLayer, transform: LayerTransform) -> OverlayLayer:
    return OverlayLayer(
        id=layer.id,
        name=layer.name,
        kind=layer.kind,
        z_index=layer.z_index,
        enabled=layer.enabled,
        locked=layer.locked,
        transform=transform,
        asset=layer.asset,
        visualizer=layer.visualizer,
    )


def make_asset_layer(
    path: str,
    *,
    media_kind: str | None = None,
    name: str | None = None,
    layer_id: str | None = None,
    rect: NormalizedRect | None = None,
    z_index: int = 10,
) -> OverlayLayer:
    suffix = Path(path).suffix.lower()
    detected = {".png": "png", ".gif": "gif"}.get(suffix)
    kind = media_kind or detected
    if kind not in ASSET_KINDS:
        raise OverlaySceneError("Somente PNG e GIF são aceitos nesta fase.")
    layer = OverlayLayer(
        id=layer_id or new_layer_id("asset"),
        name=name or Path(path).stem or "Imagem",
        kind="asset",
        z_index=z_index,
        transform=LayerTransform(rect=rect or NormalizedRect()),
        asset=AssetSpec(path=path, media_kind=kind),
    )
    layer.validate()
    return layer


def make_visualizer_layer(
    *,
    style: str = "waveform",
    name: str | None = None,
    layer_id: str | None = None,
    rect: NormalizedRect | None = None,
    z_index: int = 20,
) -> OverlayLayer:
    layer = OverlayLayer(
        id=layer_id or new_layer_id("viz"),
        name=name or {"waveform": "Waveform", "bars": "Barras", "spectrum": "Espectro"}.get(style, "Visualizador"),
        kind="visualizer",
        z_index=z_index,
        transform=LayerTransform(rect=rect or NormalizedRect(0.56, 0.82, 0.30, 0.08), preserve_aspect=False),
        visualizer=VisualizerSpec(style=style),
    )
    layer.validate()
    return layer


def next_z_index(layers: Iterable[OverlayLayer], step: int = 10) -> int:
    values = [layer.z_index for layer in layers]
    return (max(values) if values else 0) + max(1, int(step))
