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
    if "group_handle_hit = False" in text:
        return text

    old = '''    def _canvas_down(self, event) -> None:
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
'''
    new = '''    def _canvas_down(self, event) -> None:
        width, height = self._canvas_size()

        # A group resize handle can sit in empty canvas between/outside member
        # layers. Give that visible handle priority over per-layer hit testing so
        # the control the creator sees is always directly clickable.
        group_id = self.editor.group_for_selection()
        group_handle_hit = False
        if group_id:
            bounds = self.scene.group_bounds(group_id)
            gx, gy, gw, gh = bounds.pixels(width, height)
            group_handle_hit = (
                abs(event.x - (gx + gw)) <= HANDLE_SIZE * 2
                and abs(event.y - (gy + gh)) <= HANDLE_SIZE * 2
            )
            if group_handle_hit:
                group = self.scene.group(group_id)
                blocked = any(self.scene.layer(member_id).locked for member_id in group.member_ids)
                if blocked:
                    self.status_text.set("Desbloqueie todas as layers do grupo antes de redimensionar o conjunto.")
                    self._refresh_canvas()
                    return
                self._drag_mode = "resize"
                self._drag_start = (event.x, event.y)
                self._drag_origin_scene = self.scene
                self._working_scene = self.scene
                self._refresh_tree()
                self._refresh_properties()
                self._refresh_canvas()
                return

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
'''
    return replace_once(text, old, new, "group resize handle hit-test")


def main() -> None:
    original = TARGET.read_text(encoding="utf-8")
    integrated = integrate(original)
    if integrated == original:
        print("CINEPULSE_OVERLAY_GROUP_HANDLE_ALREADY_INTEGRATED")
        return
    TARGET.write_text(integrated, encoding="utf-8")
    print(f"CINEPULSE_OVERLAY_GROUP_HANDLE_OK revision={REVISION}")


if __name__ == "__main__":
    main()
