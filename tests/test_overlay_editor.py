from __future__ import annotations

import unittest

from cinepulse.overlay_composer import NormalizedRect, OverlayScene, make_asset_layer, make_visualizer_layer
from cinepulse.overlay_editor import OverlayEditorSession
from cinepulse.overlay_layout import hit_test, resize_rect, snap_rect


class OverlayEditorTests(unittest.TestCase):
    def test_hit_test_prefers_topmost_layer(self) -> None:
        back = make_asset_layer("character.png", layer_id="back", z_index=10, rect=NormalizedRect(0.2, 0.2, 0.4, 0.4))
        front = make_visualizer_layer(layer_id="front", z_index=20, rect=NormalizedRect(0.3, 0.3, 0.3, 0.2))
        scene = OverlayScene((front, back))
        self.assertEqual(hit_test(scene, 350, 220, 1000, 600), "front")
        self.assertEqual(hit_test(scene, 220, 150, 1000, 600), "back")
        self.assertIsNone(hit_test(scene, 900, 500, 1000, 600))

    def test_snap_to_canvas_center(self) -> None:
        rect = NormalizedRect(0.392, 0.40, 0.20, 0.20)
        result = snap_rect(rect, threshold=0.012)
        self.assertAlmostEqual(result.rect.x + result.rect.width / 2, 0.5)
        self.assertEqual(result.guides_x, (0.5,))

    def test_snap_to_neighbor_edge(self) -> None:
        moving = NormalizedRect(0.195, 0.20, 0.20, 0.20)
        neighbor = NormalizedRect(0.40, 0.20, 0.20, 0.20)
        result = snap_rect(moving, other_rects=(neighbor,), threshold=0.01, include_canvas=False)
        self.assertAlmostEqual(result.rect.x + result.rect.width, 0.40)
        self.assertEqual(result.guides_x, (0.40,))

    def test_resize_preserves_source_aspect(self) -> None:
        rect = NormalizedRect(0.1, 0.1, 0.2, 0.2)
        resized = resize_rect(rect, dw=0.1, dh=0.0, preserve_aspect=True, source_aspect=2.0)
        self.assertAlmostEqual(resized.width, 0.3)
        self.assertAlmostEqual(resized.height, 0.15)

    def test_editor_undo_redo_preserves_scene_and_selection(self) -> None:
        first = make_asset_layer("character.png", layer_id="asset")
        second = make_visualizer_layer(layer_id="viz")
        editor = OverlayEditorSession(OverlayScene((first,)))
        editor.select("asset")
        editor.apply(editor.scene.add_layer(second), selected_ids=("viz",))
        self.assertEqual(editor.selected_ids, ("viz",))
        self.assertTrue(editor.undo())
        self.assertEqual([layer.id for layer in editor.scene.layers], ["asset"])
        self.assertEqual(editor.selected_ids, ("asset",))
        self.assertTrue(editor.redo())
        self.assertEqual({layer.id for layer in editor.scene.layers}, {"asset", "viz"})
        self.assertEqual(editor.selected_ids, ("viz",))

    def test_group_selected_and_delete_are_undoable(self) -> None:
        first = make_asset_layer("character.png", layer_id="asset")
        second = make_visualizer_layer(layer_id="viz")
        editor = OverlayEditorSession(OverlayScene((first, second)))
        editor.select("asset", "viz")
        group_id = editor.group_selected("Character + music")
        self.assertEqual(editor.scene.group(group_id).member_ids, ("asset", "viz"))
        editor.delete_selected()
        self.assertEqual(editor.scene.layers, ())
        self.assertTrue(editor.undo())
        self.assertEqual({layer.id for layer in editor.scene.layers}, {"asset", "viz"})


if __name__ == "__main__":
    unittest.main()
