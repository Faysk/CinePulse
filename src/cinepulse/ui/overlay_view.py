"""Interactive Preview UI for CinePulse Overlay Composer.

The widget is intentionally self-contained: it owns editor selection/history and
only exposes the immutable ``OverlayScene`` to the Studio controller. This keeps
Preview experimentation away from the Stable render controller until the final
pipeline adapter is accepted.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tkinter import BooleanVar, Canvas, DoubleVar, PhotoImage, StringVar, colorchooser, filedialog, ttk
from typing import Callable

import numpy as np

from ..loop_engine import FFMPEG, FFPROBE
from ..overlay_assets import AssetFrameCache, AssetProbe, OverlayAssetError, decode_asset_rgba, probe_asset
from ..overlay_composer import (
    AssetSpec,
    LayerTransform,
    NormalizedRect,
    OverlayLayer,
    OverlayScene,
    OverlaySceneError,
    VisualizerSpec,
    make_asset_layer,
    make_visualizer_layer,
    next_z_index,
)
from ..overlay_editor import OverlayEditorSession
from ..overlay_layout import SAFE_AREAS, delta_to_normalized, hit_test, other_layer_rects, resize_rect, snap_rect
from ..overlay_presets import LAYOUT_PRESETS, apply_layout_preset, preset_summary
from ..overlay_preview import AudioReactiveState, render_scene_preview
from .preview import demo_background, demo_reactivity, resize_nearest, to_ppm_bytes


PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 360
HANDLE_SIZE = 8


class OverlayComposerView(ttk.Frame):
    def __init__(
        self,
        parent,
        *,
        scene: OverlayScene | None = None,
        on_scene_change: Callable[[OverlayScene], None] | None = None,
        base_frame_provider: Callable[[], np.ndarray | None] | None = None,
        timeline_provider: Callable[[], float] | None = None,
    ) -> None:
        super().__init__(parent, style="Card.TFrame", padding=12)
        self.editor = OverlayEditorSession(scene or OverlayScene())
        self.on_scene_change = on_scene_change
        self.base_frame_provider = base_frame_provider
        self.timeline_provider = timeline_provider
        self.asset_cache = AssetFrameCache(max_entries=36)
        self.asset_probes: dict[str, AssetProbe] = {}
        self._working_scene: OverlayScene | None = None
        self._drag_start: tuple[int, int] | None = None
        self._drag_origin_scene: OverlayScene | None = None
        self._drag_mode: str | None = None
        self._photo: PhotoImage | None = None
        self._canvas_image = None

        self.safe_area_key = StringVar(value=self.editor.scene.safe_area_profile if self.editor.scene.safe_area_profile in SAFE_AREAS else "none")
        self.layout_preset_label = StringVar(value=LAYOUT_PRESETS[0].label)
        self.status_text = StringVar(value="Adicione um PNG/GIF e um visualizador para começar.")
        self.x_var = DoubleVar(value=70.0)
        self.y_var = DoubleVar(value=68.0)
        self.width_var = DoubleVar(value=25.0)
        self.height_var = DoubleVar(value=25.0)
        self.opacity_var = DoubleVar(value=100.0)
        self.locked_var = BooleanVar(value=False)
        self.speed_var = DoubleVar(value=1.0)
        self.visualizer_style = StringVar(value="waveform")
        self.visualizer_focus = StringVar(value="full")
        self.visualizer_color = StringVar(value="#F2E5C9")
        self.sensitivity_var = DoubleVar(value=100.0)

        self._build()
        self._refresh_all()

    @property
    def scene(self) -> OverlayScene:
        return self._working_scene or self.editor.scene

    def set_scene(self, scene: OverlayScene, *, notify: bool = False) -> None:
        scene.validate()
        self.editor = OverlayEditorSession(scene)
        self._working_scene = None
        self.asset_cache.clear()
        self.asset_probes.clear()
        if notify:
            self._notify_scene_changed()
        self._refresh_all()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text="Overlay Composer · Preview", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            self,
            text=(
                "Monte PNG/GIF + gráfico musical como layers independentes. Arraste, redimensione e agrupe para mover ou escalar o conjunto como uma composição."
            ),
            style="CardMuted.TLabel",
            wraplength=700,
        ).grid(row=1, column=0, sticky="w", pady=(2, 9))

        toolbar = ttk.Frame(self, style="Card.TFrame")
        toolbar.grid(row=2, column=0, sticky="ew")
        ttk.Button(toolbar, text="+ PNG/GIF", command=self._add_asset).pack(side="left")
        ttk.Button(toolbar, text="+ Waveform", command=lambda: self._add_visualizer("waveform")).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="+ Barras", command=lambda: self._add_visualizer("bars")).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="+ Espectro", command=lambda: self._add_visualizer("spectrum")).pack(side="left", padx=(5, 0))
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="Agrupar", command=self._group_selected).pack(side="left")
        ttk.Button(toolbar, text="Desagrupar", command=self._ungroup_selected).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="Desfazer", command=self._undo).pack(side="right")
        ttk.Button(toolbar, text="Refazer", command=self._redo).pack(side="right", padx=(0, 5))

        preset_row = ttk.Frame(self, style="Card.TFrame")
        preset_row.grid(row=3, column=0, sticky="ew", pady=(7, 0))
        ttk.Label(preset_row, text="Layout rápido", style="CardMuted.TLabel").pack(side="left")
        preset_box = ttk.Combobox(
            preset_row, state="readonly", width=24, textvariable=self.layout_preset_label,
            values=tuple(item.label for item in LAYOUT_PRESETS),
        )
        preset_box.pack(side="left", padx=(6, 5))
        ttk.Button(preset_row, text="Aplicar layout", command=self._apply_layout_preset).pack(side="left")
        ttk.Label(
            preset_row, text="Reposiciona as layers; arquivos e animação permanecem intactos.",
            style="CardMuted.TLabel",
        ).pack(side="right")

        body = ttk.Frame(self, style="Card.TFrame")
        body.grid(row=4, column=0, sticky="nsew", pady=(9, 0))
        body.columnconfigure(0, weight=4, minsize=180)
        body.columnconfigure(1, weight=9, minsize=420)
        body.columnconfigure(2, weight=4, minsize=190)

        layers_panel = ttk.Frame(body, style="PanelAlt.TFrame", padding=7)
        layers_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        ttk.Label(layers_panel, text="Camadas", style="PanelAlt.TLabel").pack(anchor="w")
        self.layer_tree = ttk.Treeview(layers_panel, show="tree", height=12, selectmode="extended")
        self.layer_tree.pack(fill="both", expand=True, pady=(5, 5))
        self.layer_tree.bind("<<TreeviewSelect>>", self._tree_selected)
        layer_actions = ttk.Frame(layers_panel, style="PanelAlt.TFrame")
        layer_actions.pack(fill="x")
        ttk.Button(layer_actions, text="↑", width=3, command=lambda: self._nudge_z(1)).pack(side="left")
        ttk.Button(layer_actions, text="↓", width=3, command=lambda: self._nudge_z(-1)).pack(side="left", padx=(4, 0))
        ttk.Button(layer_actions, text="Excluir", command=self._delete_selected).pack(side="right")

        canvas_panel = ttk.Frame(body, style="PanelAlt.TFrame", padding=5)
        canvas_panel.grid(row=0, column=1, sticky="nsew", padx=7)
        self.canvas = Canvas(
            canvas_panel,
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            highlightthickness=0,
            borderwidth=0,
            background="#080B12",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._canvas_down)
        self.canvas.bind("<B1-Motion>", self._canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._canvas_up)
        self.canvas.bind("<Configure>", lambda _event: self._refresh_canvas())

        guide_row = ttk.Frame(canvas_panel, style="PanelAlt.TFrame")
        guide_row.pack(fill="x", pady=(5, 0))
        ttk.Label(guide_row, text="Guia", style="PanelAlt.TLabel").pack(side="left")
        guide = ttk.Combobox(
            guide_row,
            state="readonly",
            width=18,
            textvariable=self.safe_area_key,
            values=tuple(SAFE_AREAS.keys()),
        )
        guide.pack(side="left", padx=(5, 0))
        guide.bind("<<ComboboxSelected>>", lambda _e: self._safe_area_changed())
        ttk.Label(guide_row, textvariable=self.status_text, style="PanelAlt.TLabel").pack(side="right")

        properties = ttk.Frame(body, style="PanelAlt.TFrame", padding=7)
        properties.grid(row=0, column=2, sticky="nsew", padx=(7, 0))
        properties.columnconfigure(1, weight=1)
        ttk.Label(properties, text="Propriedades", style="PanelAlt.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")

        self._number_row(properties, 1, "X %", self.x_var)
        self._number_row(properties, 2, "Y %", self.y_var)
        self._number_row(properties, 3, "Largura %", self.width_var)
        self._number_row(properties, 4, "Altura %", self.height_var)
        self._number_row(properties, 5, "Opacidade %", self.opacity_var)
        ttk.Checkbutton(properties, text="Bloquear layer", variable=self.locked_var, command=self._apply_properties).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(5, 3)
        )

        ttk.Separator(properties).grid(row=7, column=0, columnspan=2, sticky="ew", pady=7)
        ttk.Label(properties, text="PNG / GIF", style="PanelAlt.TLabel").grid(row=8, column=0, columnspan=2, sticky="w")
        self._number_row(properties, 9, "Velocidade", self.speed_var)

        ttk.Separator(properties).grid(row=10, column=0, columnspan=2, sticky="ew", pady=7)
        ttk.Label(properties, text="Gráfico musical", style="PanelAlt.TLabel").grid(row=11, column=0, columnspan=2, sticky="w")
        ttk.Label(properties, text="Tipo", style="PanelAlt.TLabel").grid(row=12, column=0, sticky="w", pady=3)
        style_box = ttk.Combobox(properties, state="readonly", width=12, textvariable=self.visualizer_style, values=("waveform", "bars", "spectrum"))
        style_box.grid(row=12, column=1, sticky="ew", pady=3)
        style_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_properties())
        ttk.Label(properties, text="Reagir a", style="PanelAlt.TLabel").grid(row=13, column=0, sticky="w", pady=3)
        focus_box = ttk.Combobox(properties, state="readonly", width=12, textvariable=self.visualizer_focus, values=("full", "bass", "mids", "highs", "beats"))
        focus_box.grid(row=13, column=1, sticky="ew", pady=3)
        focus_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_properties())
        self._number_row(properties, 14, "Sensibilidade %", self.sensitivity_var)
        color_row = ttk.Frame(properties, style="PanelAlt.TFrame")
        color_row.grid(row=15, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(color_row, text="Cor do gráfico…", command=self._choose_visualizer_color).pack(fill="x")

    def _number_row(self, parent, row: int, label: str, variable: DoubleVar) -> None:
        ttk.Label(parent, text=label, style="PanelAlt.TLabel").grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Spinbox(parent, textvariable=variable, from_=-200, to=400, increment=1, width=9, command=self._apply_properties)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        entry.bind("<Return>", lambda _e: self._apply_properties())
        entry.bind("<FocusOut>", lambda _e: self._apply_properties())

    def _apply_layout_preset(self) -> None:
        chosen = next((item for item in LAYOUT_PRESETS if item.label == self.layout_preset_label.get()), LAYOUT_PRESETS[0])
        selected_layers = []
        for layer_id in self.editor.selected_ids:
            try:
                selected_layers.append(self.scene.layer(layer_id))
            except OverlaySceneError:
                continue
        asset_id = next((layer.id for layer in selected_layers if layer.kind == "asset"), None)
        visualizer_id = next((layer.id for layer in selected_layers if layer.kind == "visualizer"), None)
        try:
            result = apply_layout_preset(
                self.scene,
                chosen.key,
                asset_layer_id=asset_id,
                visualizer_layer_id=visualizer_id,
            )
            if asset_id is None:
                asset_id = next((layer.id for layer in result.ordered_layers if layer.kind == "asset"), None)
            if visualizer_id is None:
                visualizer_id = next((layer.id for layer in result.ordered_layers if layer.kind == "visualizer"), None)
            selected = tuple(layer_id for layer_id in (asset_id, visualizer_id) if layer_id)
            self.editor.apply(result, selected_ids=selected)
            self.safe_area_key.set(result.safe_area_profile)
            self.status_text.set(preset_summary(chosen.key))
            self._notify_scene_changed()
            self._refresh_all()
        except OverlaySceneError as exc:
            self.status_text.set(str(exc))

    def _add_asset(self) -> None:
        path = filedialog.askopenfilename(
            title="Adicionar PNG ou GIF",
            filetypes=(("PNG ou GIF", "*.png *.gif"), ("PNG", "*.png"), ("GIF", "*.gif")),
        )
        if not path:
            return
        try:
            probe = probe_asset(str(FFPROBE), path)
            aspect = probe.width / max(1, probe.height)
            width = 0.24
            height = width * (PREVIEW_WIDTH / PREVIEW_HEIGHT) / max(aspect, 1e-6)
            rect = NormalizedRect(0.72, max(0.05, 0.90 - height), width, min(0.80, height))
            layer = make_asset_layer(
                path,
                rect=rect,
                z_index=next_z_index(self.scene.layers),
            )
            self.asset_probes[layer.id] = probe
            self.editor.apply(self.scene.add_layer(layer), selected_ids=(layer.id,))
            self.status_text.set(f"{Path(path).name} adicionado")
            self._notify_scene_changed()
            self._refresh_all()
        except (OverlayAssetError, OverlaySceneError) as exc:
            self.status_text.set(str(exc))

    def _add_visualizer(self, style: str) -> None:
        layer = make_visualizer_layer(style=style, z_index=next_z_index(self.scene.layers))
        self.editor.apply(self.scene.add_layer(layer), selected_ids=(layer.id,))
        self.status_text.set(f"{layer.name} adicionado")
        self._notify_scene_changed()
        self._refresh_all()

    def _delete_selected(self) -> None:
        if not self.editor.selected_ids:
            return
        self.editor.delete_selected()
        self._notify_scene_changed()
        self._refresh_all()

    def _group_selected(self) -> None:
        try:
            self.editor.group_selected("Composição")
            self.status_text.set("Camadas agrupadas")
            self._notify_scene_changed()
            self._refresh_all()
        except OverlaySceneError as exc:
            self.status_text.set(str(exc))

    def _ungroup_selected(self) -> None:
        if self.editor.ungroup_selected():
            self.status_text.set("Grupo desfeito")
            self._notify_scene_changed()
            self._refresh_all()

    def _undo(self) -> None:
        if self.editor.undo():
            self._notify_scene_changed()
            self._refresh_all()

    def _redo(self) -> None:
        if self.editor.redo():
            self._notify_scene_changed()
            self._refresh_all()

    def _nudge_z(self, delta: int) -> None:
        if len(self.editor.selected_ids) != 1:
            return
        layer = self.scene.layer(self.editor.selected_ids[0])
        replacement = replace(layer, z_index=layer.z_index + int(delta) * 10)
        self.editor.apply(self.scene.replace_layer(replacement))
        self._notify_scene_changed()
        self._refresh_all()

    def _tree_selected(self, _event=None) -> None:
        selected = tuple(self.layer_tree.selection())
        self.editor.select(*selected)
        self._refresh_properties()
        self._refresh_canvas()

    def _selected_layer(self) -> OverlayLayer | None:
        if len(self.editor.selected_ids) != 1:
            return None
        try:
            return self.scene.layer(self.editor.selected_ids[0])
        except OverlaySceneError:
            return None

    def _refresh_tree(self) -> None:
        current = set(self.editor.selected_ids)
        for item in self.layer_tree.get_children():
            self.layer_tree.delete(item)
        labels = {"asset": "Imagem", "visualizer": "Áudio"}
        for layer in reversed(self.scene.ordered_layers):
            marker = "🔒 " if layer.locked else ""
            state = "" if layer.enabled else " (oculta)"
            self.layer_tree.insert("", "end", iid=layer.id, text=f"{marker}{layer.name} · {labels[layer.kind]}{state}")
        for layer_id in current:
            if self.layer_tree.exists(layer_id):
                self.layer_tree.selection_add(layer_id)

    def _refresh_properties(self) -> None:
        layer = self._selected_layer()
        if layer is None:
            return
        rect = layer.transform.rect
        self.x_var.set(round(rect.x * 100, 2))
        self.y_var.set(round(rect.y * 100, 2))
        self.width_var.set(round(rect.width * 100, 2))
        self.height_var.set(round(rect.height * 100, 2))
        self.opacity_var.set(round(layer.transform.opacity * 100, 2))
        self.locked_var.set(layer.locked)
        if layer.asset is not None:
            self.speed_var.set(layer.asset.speed)
        if layer.visualizer is not None:
            self.visualizer_style.set(layer.visualizer.style)
            self.visualizer_focus.set(layer.visualizer.focus)
            self.visualizer_color.set(layer.visualizer.color)
            self.sensitivity_var.set(layer.visualizer.sensitivity * 100.0)

    def _apply_properties(self) -> None:
        layer = self._selected_layer()
        if layer is None:
            return
        try:
            rect = NormalizedRect(
                float(self.x_var.get()) / 100.0,
                float(self.y_var.get()) / 100.0,
                max(0.001, float(self.width_var.get()) / 100.0),
                max(0.001, float(self.height_var.get()) / 100.0),
            )
            transform = LayerTransform(
                rect=rect,
                opacity=max(0.0, min(1.0, float(self.opacity_var.get()) / 100.0)),
                rotation_deg=layer.transform.rotation_deg,
                preserve_aspect=layer.transform.preserve_aspect,
            )
            asset = layer.asset
            visualizer = layer.visualizer
            if asset is not None:
                asset = AssetSpec(asset.path, asset.media_kind, asset.loop, max(0.05, min(8.0, float(self.speed_var.get()))))
            if visualizer is not None:
                visualizer = replace(
                    visualizer,
                    style=self.visualizer_style.get(),
                    focus=self.visualizer_focus.get(),
                    color=self.visualizer_color.get(),
                    sensitivity=max(0.05, min(8.0, float(self.sensitivity_var.get()) / 100.0)),
                )
            replacement = replace(layer, transform=transform, locked=self.locked_var.get(), asset=asset, visualizer=visualizer)
            self.editor.apply(self.scene.replace_layer(replacement))
            self._notify_scene_changed()
            self._refresh_tree()
            self._refresh_canvas()
        except (ValueError, OverlaySceneError) as exc:
            self.status_text.set(str(exc))

    def _choose_visualizer_color(self) -> None:
        layer = self._selected_layer()
        if layer is None or layer.visualizer is None:
            return
        value = colorchooser.askcolor(initialcolor=layer.visualizer.color, title="Cor do visualizador")[1]
        if value:
            self.visualizer_color.set(value.upper())
            self._apply_properties()

    def _safe_area_changed(self) -> None:
        key = self.safe_area_key.get()
        if key not in SAFE_AREAS:
            return
        scene = OverlayScene(self.scene.layers, self.scene.groups, self.scene.schema, key)
        self.editor.apply(scene)
        self.status_text.set(SAFE_AREAS[key].note)
        self._notify_scene_changed()
        self._refresh_canvas()

    def _canvas_size(self) -> tuple[int, int]:
        width = max(64, self.canvas.winfo_width())
        height = max(36, self.canvas.winfo_height())
        return width, height

    def _canvas_down(self, event) -> None:
        width, height = self._canvas_size()
        layer_id = hit_test(self.scene, event.x, event.y, width, height)
        if layer_id is None:
            self.editor.clear_selection()
            self._refresh_tree()
            self._refresh_properties()
            self._refresh_canvas()
            return
        self.editor.select(layer_id)
        layer = self.scene.layer(layer_id)
        group_id = self.editor.group_for_selection()
        drag_rect = layer.transform.rect
        blocked = layer.locked
        if group_id:
            group = self.scene.group(group_id)
            blocked = any(self.scene.layer(member_id).locked for member_id in group.member_ids)
            drag_rect = self.scene.group_bounds(group_id)
        x, y, w, h = drag_rect.pixels(width, height)
        near_handle = abs(event.x - (x + w)) <= HANDLE_SIZE * 2 and abs(event.y - (y + h)) <= HANDLE_SIZE * 2
        if blocked:
            self.status_text.set("Desbloqueie todas as layers do grupo antes de mover ou redimensionar o conjunto.")
            self._drag_start = None
            self._drag_origin_scene = None
            self._working_scene = None
            self._drag_mode = None
            self._refresh_tree()
            self._refresh_properties()
            self._refresh_canvas()
            return
        self._drag_mode = "resize" if near_handle else "move"
        self._drag_start = (event.x, event.y)
        self._drag_origin_scene = self.scene
        self._working_scene = self.scene
        self._refresh_tree()
        self._refresh_properties()
        self._refresh_canvas()

    def _canvas_drag(self, event) -> None:
        if self._drag_start is None or self._drag_origin_scene is None or not self.editor.selected_ids:
            return
        width, height = self._canvas_size()
        dx_px = event.x - self._drag_start[0]
        dy_px = event.y - self._drag_start[1]
        dx, dy = delta_to_normalized(dx_px, dy_px, width, height)
        selected_id = self.editor.selected_ids[0]
        layer = self._drag_origin_scene.layer(selected_id)
        if layer.locked:
            return

        group_id = self.editor.group_for_selection()
        try:
            if group_id:
                group = self._drag_origin_scene.group(group_id)
                if any(self._drag_origin_scene.layer(member_id).locked for member_id in group.member_ids):
                    self.status_text.set("Grupo contém layer bloqueada; transformação cancelada para preservar a composição.")
                    return
            if self._drag_mode == "move" and group_id:
                scene = self._drag_origin_scene.move_group(group_id, dx, dy)
            elif self._drag_mode == "move":
                moved = layer.transform.rect.moved(dx, dy)
                snapped = snap_rect(
                    moved,
                    other_rects=other_layer_rects(self._drag_origin_scene, (selected_id,)),
                    safe_area_key=self.safe_area_key.get(),
                )
                transform = replace(layer.transform, rect=snapped.rect)
                scene = self._drag_origin_scene.replace_layer(replace(layer, transform=transform))
            elif group_id:
                bounds = self._drag_origin_scene.group_bounds(group_id)
                factor_x = (bounds.width + dx) / max(bounds.width, 1e-9)
                factor_y = (bounds.height + dy) / max(bounds.height, 1e-9)
                factor = factor_x if abs(factor_x - 1.0) >= abs(factor_y - 1.0) else factor_y
                factor = max(0.05, min(20.0, factor))
                scene = self._drag_origin_scene.scale_group(group_id, factor)
            else:
                source_aspect = None
                probe = self.asset_probes.get(selected_id)
                if probe is not None:
                    source_aspect = (probe.width / probe.height) * (height / width)
                rect = resize_rect(
                    layer.transform.rect,
                    dw=dx,
                    dh=dy,
                    preserve_aspect=layer.transform.preserve_aspect,
                    source_aspect=source_aspect,
                )
                scene = self._drag_origin_scene.replace_layer(replace(layer, transform=replace(layer.transform, rect=rect)))
            self._working_scene = scene
            self._refresh_canvas()
        except OverlaySceneError as exc:
            self.status_text.set(str(exc))

    def _canvas_up(self, _event) -> None:
        if self._working_scene is not None and self._drag_origin_scene is not None and self._working_scene != self._drag_origin_scene:
            final_scene = self._working_scene
            self._working_scene = None
            self.editor.apply(final_scene)
            self._notify_scene_changed()
        self._working_scene = None
        self._drag_start = None
        self._drag_origin_scene = None
        self._drag_mode = None
        self._refresh_all()

    def _timeline_seconds(self) -> float:
        if self.timeline_provider is None:
            return 2.3
        try:
            return max(0.0, float(self.timeline_provider()))
        except Exception:
            return 2.3

    def _base_frame(self, width: int, height: int) -> np.ndarray:
        base = None
        if self.base_frame_provider is not None:
            try:
                base = self.base_frame_provider()
            except Exception:
                base = None
        if base is None:
            return demo_background(width, height)
        return resize_nearest(base, width, height)

    def _asset_frames(self, scene: OverlayScene, width: int, height: int) -> dict[str, np.ndarray]:
        frames: dict[str, np.ndarray] = {}
        seconds = self._timeline_seconds()
        for layer in scene.active_layers:
            if layer.asset is None:
                continue
            x, y, target_w, target_h = layer.transform.rect.pixels(width, height)
            _ = (x, y)
            try:
                probe = self.asset_probes.get(layer.id)
                if probe is None:
                    probe = probe_asset(str(FFPROBE), layer.asset.path)
                    self.asset_probes[layer.id] = probe
                frames[layer.id] = decode_asset_rgba(
                    str(FFMPEG),
                    layer.asset.path,
                    width=target_w,
                    height=target_h,
                    timeline_seconds=seconds,
                    duration=probe.duration,
                    speed=layer.asset.speed,
                    loop=layer.asset.loop,
                    preserve_aspect=layer.transform.preserve_aspect,
                    cache=self.asset_cache,
                )
            except OverlayAssetError as exc:
                self.status_text.set(str(exc))
        return frames

    def _audio_state(self) -> AudioReactiveState:
        seconds = self._timeline_seconds()
        frame_number = int(round(seconds * 60.0))
        bands, loudness, attack = demo_reactivity(frame_number)
        return AudioReactiveState(tuple(float(value) for value in bands[:3]), float(loudness), float(attack), (seconds % 6.0) / 6.0)

    def _refresh_canvas(self) -> None:
        if not self.canvas.winfo_exists():
            return
        width, height = self._canvas_size()
        scene = self.scene
        base = self._base_frame(width, height)
        frames = self._asset_frames(scene, width, height)
        image = render_scene_preview(base, scene, asset_frames=frames, audio_state=self._audio_state())
        self._photo = PhotoImage(data=to_ppm_bytes(image), format="PPM")
        self.canvas.delete("all")
        self._canvas_image = self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        guide = SAFE_AREAS.get(self.safe_area_key.get())
        if guide and guide.key != "none":
            gx, gy, gw, gh = guide.rect.pixels(width, height)
            self.canvas.create_rectangle(gx, gy, gx + gw, gy + gh, outline="#D2B46A", dash=(5, 4), width=1)

        selected = set(self.editor.selected_ids)
        group_id = self.editor.group_for_selection()
        if group_id:
            group = scene.group(group_id)
            bounds = scene.group_bounds(group_id)
            x, y, w, h = bounds.pixels(width, height)
            blocked = any(scene.layer(member_id).locked for member_id in group.member_ids)
            color = "#A7AFBE" if blocked else "#F3D28B"
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=2, dash=(5, 3))
            if not blocked:
                hs = HANDLE_SIZE
                self.canvas.create_rectangle(x + w - hs, y + h - hs, x + w + hs, y + h + hs, fill=color, outline="")
        else:
            for layer in scene.active_layers:
                if layer.id not in selected:
                    continue
                x, y, w, h = layer.transform.rect.pixels(width, height)
                color = "#F3D28B" if not layer.locked else "#A7AFBE"
                self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=2)
                if not layer.locked:
                    hs = HANDLE_SIZE
                    self.canvas.create_rectangle(x + w - hs, y + h - hs, x + w + hs, y + h + hs, fill=color, outline="")

    def _refresh_all(self) -> None:
        self._refresh_tree()
        self._refresh_properties()
        self.after_idle(self._refresh_canvas)

    def _notify_scene_changed(self) -> None:
        scene = self.editor.scene
        if self.on_scene_change is not None:
            self.on_scene_change(scene)
