from __future__ import annotations

import unittest

from cinepulse.overlay_composer import OverlayGroup, OverlayScene, OverlaySceneError, make_asset_layer, make_visualizer_layer
from cinepulse.overlay_presets import apply_layout_preset, preset, preset_summary


class OverlayPresetTests(unittest.TestCase):
    def test_character_waveform_layout_positions_and_groups_pair(self) -> None:
        asset = make_asset_layer("character.png", layer_id="asset")
        visualizer = make_visualizer_layer(layer_id="viz", style="bars")
        scene = apply_layout_preset(OverlayScene((visualizer, asset)), "character-wave-right")
        moved_asset = scene.layer("asset")
        moved_viz = scene.layer("viz")
        self.assertAlmostEqual(moved_asset.transform.rect.x, 0.72)
        self.assertAlmostEqual(moved_asset.transform.rect.width, 0.22)
        self.assertAlmostEqual(moved_viz.transform.rect.y, 0.84)
        self.assertEqual(moved_viz.visualizer.style, "waveform")
        self.assertEqual(moved_viz.visualizer.focus, "bass")
        self.assertEqual(len(scene.groups), 1)
        self.assertEqual(set(scene.groups[0].member_ids), {"asset", "viz"})
        self.assertEqual(scene.safe_area_profile, "frame")

    def test_wide_waveform_keeps_pair_ungrouped(self) -> None:
        scene = OverlayScene((
            make_asset_layer("character.png", layer_id="asset"),
            make_visualizer_layer(layer_id="viz", style="bars"),
        ))
        result = apply_layout_preset(scene, "wide-wave-bottom")
        self.assertEqual(result.groups, ())
        self.assertAlmostEqual(result.layer("viz").transform.rect.width, 0.84)
        self.assertEqual(result.layer("viz").visualizer.style, "waveform")

    def test_visualizer_only_scene_can_use_minimal_preset(self) -> None:
        scene = OverlayScene((make_visualizer_layer(layer_id="viz"),))
        result = apply_layout_preset(scene, "minimal-spectrum")
        self.assertEqual(result.layer("viz").visualizer.style, "spectrum")
        self.assertAlmostEqual(result.layer("viz").transform.rect.x, 0.20)
        self.assertEqual(result.groups, ())

    def test_existing_group_touching_pair_is_replaced_but_unrelated_group_survives(self) -> None:
        asset = make_asset_layer("character.png", layer_id="asset")
        visualizer = make_visualizer_layer(layer_id="viz")
        other_a = make_asset_layer("other-a.png", layer_id="other-a")
        other_b = make_visualizer_layer(layer_id="other-b")
        scene = OverlayScene(
            (asset, visualizer, other_a, other_b),
            (
                OverlayGroup("old", "Old", ("asset", "viz")),
                OverlayGroup("other", "Other", ("other-a", "other-b")),
            ),
        )
        result = apply_layout_preset(scene, "character-bars-right", asset_layer_id="asset", visualizer_layer_id="viz")
        self.assertNotIn("old", {group.id for group in result.groups})
        self.assertIn("other", {group.id for group in result.groups})
        pair = next(group for group in result.groups if group.id != "other")
        self.assertEqual(set(pair.member_ids), {"asset", "viz"})

    def test_layout_requires_visualizer(self) -> None:
        scene = OverlayScene((make_asset_layer("character.png", layer_id="asset"),))
        with self.assertRaises(OverlaySceneError):
            apply_layout_preset(scene, "character-wave-right")

    def test_unknown_preset_is_rejected(self) -> None:
        with self.assertRaises(OverlaySceneError):
            preset("does-not-exist")

    def test_summary_is_human_readable(self) -> None:
        text = preset_summary("character-wave-right")
        self.assertIn("Personagem + Waveform", text)
        self.assertIn("canto direito", text)


if __name__ == "__main__":
    unittest.main()
