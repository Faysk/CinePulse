from __future__ import annotations

from dataclasses import dataclass

from .overlay_composer import OverlayGroup, OverlayScene, OverlaySceneError, new_layer_id


@dataclass(frozen=True)
class EditorSnapshot:
    scene: OverlayScene
    selected_ids: tuple[str, ...]


class OverlayEditorSession:
    """Mutable editor shell around immutable overlay scenes.

    Rendering consumes ``scene`` only. Selection/undo are editor concerns and do
    not leak into project serialization, which keeps render fingerprints stable.
    """

    def __init__(self, scene: OverlayScene | None = None, *, history_limit: int = 60) -> None:
        self.scene = scene or OverlayScene()
        self.scene.validate()
        self.selected_ids: tuple[str, ...] = ()
        self.history_limit = max(2, int(history_limit))
        self._undo: list[EditorSnapshot] = []
        self._redo: list[EditorSnapshot] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _snapshot(self) -> EditorSnapshot:
        return EditorSnapshot(self.scene, self.selected_ids)

    def _push_undo(self) -> None:
        self._undo.append(self._snapshot())
        if len(self._undo) > self.history_limit:
            del self._undo[0 : len(self._undo) - self.history_limit]
        self._redo.clear()

    def apply(self, scene: OverlayScene, *, selected_ids: tuple[str, ...] | None = None) -> None:
        scene.validate()
        if scene == self.scene and (selected_ids is None or selected_ids == self.selected_ids):
            return
        self._push_undo()
        self.scene = scene
        if selected_ids is not None:
            self.select(*selected_ids)
        else:
            self._drop_missing_selection()

    def select(self, *layer_ids: str, additive: bool = False) -> None:
        valid = {layer.id for layer in self.scene.layers}
        incoming = [layer_id for layer_id in layer_ids if layer_id in valid]
        if additive:
            ordered = list(self.selected_ids)
            for layer_id in incoming:
                if layer_id not in ordered:
                    ordered.append(layer_id)
            self.selected_ids = tuple(ordered)
        else:
            self.selected_ids = tuple(dict.fromkeys(incoming))

    def clear_selection(self) -> None:
        self.selected_ids = ()

    def _drop_missing_selection(self) -> None:
        valid = {layer.id for layer in self.scene.layers}
        self.selected_ids = tuple(layer_id for layer_id in self.selected_ids if layer_id in valid)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        snapshot = self._undo.pop()
        self.scene = snapshot.scene
        self.selected_ids = snapshot.selected_ids
        self._drop_missing_selection()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        snapshot = self._redo.pop()
        self.scene = snapshot.scene
        self.selected_ids = snapshot.selected_ids
        self._drop_missing_selection()
        return True

    def delete_selected(self) -> None:
        if not self.selected_ids:
            return
        scene = self.scene
        for layer_id in self.selected_ids:
            scene = scene.remove_layer(layer_id)
        self.apply(scene, selected_ids=())

    def group_selected(self, name: str = "Grupo") -> str:
        members = tuple(dict.fromkeys(self.selected_ids))
        if len(members) < 2:
            raise OverlaySceneError("Selecione pelo menos duas layers para agrupar.")
        group_id = new_layer_id("group")
        self.apply(self.scene.add_group(OverlayGroup(group_id, name, members)), selected_ids=members)
        return group_id

    def ungroup_selected(self) -> bool:
        selected = set(self.selected_ids)
        for group in self.scene.groups:
            if selected.intersection(group.member_ids):
                self.apply(self.scene.remove_group(group.id))
                return True
        return False

    def group_for_selection(self) -> str | None:
        selected = set(self.selected_ids)
        if not selected:
            return None
        for group in self.scene.groups:
            if selected.issubset(set(group.member_ids)):
                return group.id
        return None
