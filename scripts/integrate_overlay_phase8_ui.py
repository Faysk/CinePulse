from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "cinepulse" / "ui" / "overlay_view.py"
REVISION = 1


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def integrate(text: str) -> str:
    if "def _apply_layout_preset" in text and "scale_group(group_id" in text:
        return text

    text = replace_once(
        text,
        "from ..overlay_layout import SAFE_AREAS, delta_to_normalized, hit_test, other_layer_rects, resize_rect, snap_rect\n"
        "from ..overlay_preview import AudioReactiveState, render_scene_preview\n",
        "from ..overlay_layout import SAFE_AREAS, delta_to_normalized, hit_test, other_layer_rects, resize_rect, snap_rect\n"
        "from ..overlay_presets import LAYOUT_PRESETS, apply_layout_preset, preset_summary\n"
        "from ..overlay_preview import AudioReactiveState, render_scene_preview\n",
        "preset import",
    )
    text = replace_once(
        text,
        "        self.safe_area_key = StringVar(value=self.editor.scene.safe_area_profile if self.editor.scene.safe_area_profile in SAFE_AREAS else \"none\")\n"
        "        self.status_text = StringVar(value=\"Adicione um PNG/GIF e um visualizador para começar.\")\n",
        "        self.safe_area_key = StringVar(value=self.editor.scene.safe_area_profile if self.editor.scene.safe_area_profile in SAFE_AREAS else \"none\")\n"
        "        self.layout_preset_label = StringVar(value=LAYOUT_PRESETS[0].label)\n"
        "        self.status_text = StringVar(value=\"Adicione um PNG/GIF e um visualizador para começar.\")\n",
        "preset state",
    )
    text = replace_once(
        text,
        "                \"Monte PNG/GIF + gráfico musical como layers independentes. Arraste no canvas, redimensione pelo canto e agrupe quando quiser mover o conjunto.\"\n",
        "                \"Monte PNG/GIF + gráfico musical como layers independentes. Arraste, redimensione e agrupe para mover ou escalar o conjunto como uma composição.\"\n",
        "composer description",
    )
    text = replace_once(
        text,
        "        ttk.Button(toolbar, text=\"Desagrupar\", command=self._ungroup_selected).pack(side=\"left\", padx=(5, 0))\n"
        "        ttk.Button(toolbar, text=\"Desfazer\", command=self._undo).pack(side=\"right\")\n"
        "        ttk.Button(toolbar, text=\"Refazer\", command=self._redo).pack(side=\"right\", padx=(0, 5))\n\n"
        "        body = ttk.Frame(self, style=\"Card.TFrame\")\n"
        "        body.grid(row=3, column=0, sticky=\"nsew\", pady=(9, 0))\n",
        "        ttk.Button(toolbar, text=\"Desagrupar\", command=self._ungroup_selected).pack(side=\"left\", padx=(5, 0))\n"
        "        ttk.Button(toolbar, text=\"Desfazer\", command=self._undo).pack(side=\"right\")\n"
        "        ttk.Button(toolbar, text=\"Refazer\", command=self._redo).pack(side=\"right\", padx=(0, 5))\n\n"
        "        preset_row = ttk.Frame(self, style=\"Card.TFrame\")\n"
        "        preset_row.grid(row=3, column=0, sticky=\"ew\", pady=(7, 0))\n"
        "        ttk.Label(preset_row, text=\"Layout rápido\", style=\"CardMuted.TLabel\").pack(side=\"left\")\n"
        "        preset_box = ttk.Combobox(\n"
        "            preset_row, state=\"readonly\", width=24, textvariable=self.layout_preset_label,\n"
        "            values=tuple(item.label for item in LAYOUT_PRESETS),\n"
        "        )\n"
        "        preset_box.pack(side=\"left\", padx=(6, 5))\n"
        "        ttk.Button(preset_row, text=\"Aplicar layout\", command=self._apply_layout_preset).pack(side=\"left\")\n"
        "        ttk.Label(\n"
        "            preset_row, text=\"Reposiciona as layers; arquivos e animação permanecem intactos.\",\n"
        "            style=\"CardMuted.TLabel\",\n"
        "        ).pack(side=\"right\")\n\n"
        "        body = ttk.Frame(self, style=\"Card.TFrame\")\n"
        "        body.grid(row=4, column=0, sticky=\"nsew\", pady=(9, 0))\n",
        "preset toolbar",
    )

    method_anchor = "    def _add_asset(self) -> None:\n"
    preset_method = '''    def _apply_layout_preset(self) -> None:
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

'''
    text = replace_once(text, method_anchor, preset_method + method_anchor, "preset method")

    old_down = '''        self.editor.select(layer_id)
        layer = self.scene.layer(layer_id)
        x, y, w, h = layer.transform.rect.pixels(width, height)
        near_handle = abs(event.x - (x + w)) <= HANDLE_SIZE * 2 and abs(event.y - (y + h)) <= HANDLE_SIZE * 2
        self._drag_mode = "resize" if near_handle and not layer.locked else "move"
        self._drag_start = (event.x, event.y)
        self._drag_origin_scene = self.scene
        self._working_scene = self.scene
'''
    new_down = '''        self.editor.select(layer_id)
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
'''
    text = replace_once(text, old_down, new_down, "group-aware canvas down")

    old_drag = '''        group_id = self.editor.group_for_selection()
        try:
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
'''
    new_drag = '''        group_id = self.editor.group_for_selection()
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
'''
    text = replace_once(text, old_drag, new_drag, "group resize")

    old_selection = '''        selected = set(self.editor.selected_ids)
        for layer in scene.active_layers:
            if layer.id not in selected:
                continue
            x, y, w, h = layer.transform.rect.pixels(width, height)
            color = "#F3D28B" if not layer.locked else "#A7AFBE"
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=2)
            if not layer.locked:
                hs = HANDLE_SIZE
                self.canvas.create_rectangle(x + w - hs, y + h - hs, x + w + hs, y + h + hs, fill=color, outline="")
'''
    new_selection = '''        selected = set(self.editor.selected_ids)
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
'''
    text = replace_once(text, old_selection, new_selection, "group selection frame")
    return text


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    integrated = integrate(original)
    if integrated == original:
        print("CINEPULSE_OVERLAY_PHASE8_UI_ALREADY_INTEGRATED")
        return
    TARGET.write_text(integrated, encoding="utf-8")
    print(f"CINEPULSE_OVERLAY_PHASE8_UI_OK revision={REVISION}")


if __name__ == "__main__":
    main()
