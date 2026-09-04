from __future__ import annotations

import unittest

from cinepulse.overlay_composer import (
    AssetSpec,
    LayerTransform,
    NormalizedRect,
    OverlayGroup,
    OverlayLayer,
    OverlayScene,
    OverlaySceneError,
    VisualizerSpec,
    make_asset_layer,
    make_visualizer_layer,
)


class OverlayComposerTests(unittest.TestCase):
    def test_normalized_rect_scales_to_any_canvas(self) -> None:
        rect = NormalizedRect(0.75, 0.50, 0.20, 0.10)
        self.assertEqual(rect.pixels(1920, 1080), (1440, 540, 384, 108))
        self.assertEqual(rect.pixels(3840, 2160), (2880, 1080, 768, 216))

    def test_png_and_visualizer_are_independent_layers(self) -> None:
        image = make_asset_layer(
            "character.png",
            layer_id="asset-1",
            rect=NormalizedRect(0.73, 0.61, 0.22, 0.31),
        )
        viz = make_visualizer_layer(
            style="waveform",
            layer_id="viz-1",
            rect=NormalizedRect(0.55, 0.84, 0.31, 0.06),
        )
        scene = OverlayScene((image, viz))
        scene.validate()
        self.assertEqual(scene.layer("asset-1").transform.rect.width, 0.22)
        self.assertEqual(scene.layer("viz-1").transform.rect.width, 0.31)
        self.assertNotEqual(scene.layer("asset-1").transform.rect.height, scene.layer("viz-1").transform.rect.height)

    def test_group_move_preserves_internal_spacing(self) -> None:
        image = make_asset_layer(
            "character.png", layer_id="asset-1", rect=NormalizedRect(0.70, 0.60, 0.20, 0.25)
        )
        viz = make_visualizer_layer(
            layer_id="viz-1", rect=NormalizedRect(0.55, 0.84, 0.30, 0.06)
        )
        scene = OverlayScene((image, viz), (OverlayGroup("group-1", "Hero + waveform", ("asset-1", "viz-1")),))
        moved = scene.move_group("group-1", -0.10, 0.03)
        self.assertAlmostEqual(moved.layer("asset-1").transform.rect.x, 0.60)
        self.assertAlmostEqual(moved.layer("viz-1").transform.rect.x, 0.45)
        spacing_before = image.transform.rect.x - viz.transform.rect.x
        spacing_after = moved.layer("asset-1").transform.rect.x - moved.layer("viz-1").transform.rect.x
        self.assertAlmostEqual(spacing_before, spacing_after)

    def test_group_scale_uses_group_center(self) -> None:
        image = make_asset_layer(
            "character.png", layer_id="asset-1", rect=NormalizedRect(0.70, 0.60, 0.20, 0.25)
        )
        viz = make_visualizer_layer(
            layer_id="viz-1", rect=NormalizedRect(0.55, 0.84, 0.30, 0.06)
        )
        scene = OverlayScene((image, viz), (OverlayGroup("group-1", "Hero + waveform", ("asset-1", "viz-1")),))
        before = scene.group_bounds("group-1")
        scaled = scene.scale_group("group-1", 0.5)
        after = scaled.group_bounds("group-1")
        self.assertAlmostEqual(after.width, before.width * 0.5)
        self.assertAlmostEqual(after.height, before.height * 0.5)
        self.assertAlmostEqual(after.x + after.width / 2, before.x + before.width / 2)
        self.assertAlmostEqual(after.y + after.height / 2, before.y + before.height / 2)

    def test_locked_layer_is_not_changed_by_group_edit(self) -> None:
        image = OverlayLayer(
            id="asset-1",
            name="Locked",
            kind="asset",
            locked=True,
            asset=AssetSpec("character.png", "png"),
            transform=LayerTransform(NormalizedRect(0.7, 0.6, 0.2, 0.2)),
        )
        viz = make_visualizer_layer(layer_id="viz-1")
        scene = OverlayScene((image, viz), (OverlayGroup("group-1", "Group", ("asset-1", "viz-1")),))
        moved = scene.move_group("group-1", 0.1, 0.1)
        self.assertEqual(moved.layer("asset-1").transform.rect, image.transform.rect)
        self.assertNotEqual(moved.layer("viz-1").transform.rect, viz.transform.rect)

    def test_scene_roundtrip_and_fingerprint_are_deterministic(self) -> None:
        image = make_asset_layer("character.gif", layer_id="asset-1", media_kind="gif")
        viz = OverlayLayer(
            id="viz-1",
            name="Jazz waveform",
            kind="visualizer",
            z_index=20,
            transform=LayerTransform(NormalizedRect(0.50, 0.82, 0.34, 0.07), opacity=0.75, preserve_aspect=False),
            visualizer=VisualizerSpec(style="bars", color="#F0E0C0", bars=48, focus="bass"),
        )
        scene = OverlayScene((image, viz), (OverlayGroup("group-1", "Jazz badge", ("asset-1", "viz-1")),))
        restored = OverlayScene.from_json(scene.to_json())
        self.assertEqual(restored.to_dict(), scene.to_dict())
        self.assertEqual(restored.fingerprint, scene.fingerprint)

    def test_z_order_is_stable_even_when_input_order_differs(self) -> None:
        top = make_visualizer_layer(layer_id="viz-top", z_index=30)
        back = make_asset_layer("character.png", layer_id="asset-back", z_index=10)
        scene = OverlayScene((top, back))
        self.assertEqual([layer.id for layer in scene.ordered_layers], ["asset-back", "viz-top"])

    def test_future_schema_and_invalid_group_are_rejected(self) -> None:
        with self.assertRaises(OverlaySceneError):
            OverlayScene.from_dict({"schema": "cinepulse.overlay-scene/99", "layers": [], "groups": []})

        image = make_asset_layer("character.png", layer_id="asset-1")
        scene = OverlayScene((image,), (OverlayGroup("group-1", "Broken", ("asset-1", "missing")),))
        with self.assertRaises(OverlaySceneError):
            scene.validate()

    def test_asset_extension_contract_prevents_silent_mismatch(self) -> None:
        layer = OverlayLayer(
            id="bad",
            name="Bad",
            kind="asset",
            asset=AssetSpec("animation.gif", "png"),
        )
        with self.assertRaises(OverlaySceneError):
            layer.validate()


if __name__ == "__main__":
    unittest.main()
