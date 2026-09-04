from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.overlay_composer import OverlayScene, VisualizerSpec, OverlayLayer, make_asset_layer
from cinepulse.overlay_runtime import has_assets, has_visualizer, scene_from_json, scene_to_json, summary, validate_scene_sources


class OverlayRuntimeTests(unittest.TestCase):
    def test_empty_payload_is_backward_compatible(self) -> None:
        scene = scene_from_json("")
        self.assertEqual(scene, OverlayScene())
        self.assertEqual(scene_to_json(scene), scene.to_json())
        self.assertEqual(summary(scene), "sem overlays")

    def test_missing_asset_blocks_before_render(self) -> None:
        scene = OverlayScene((make_asset_layer("missing-character.png", layer_id="asset"),))
        result = validate_scene_sources(scene, audio_available=True)
        self.assertFalse(result.ok)
        self.assertIn("arquivo não encontrado", result.errors[0])

    def test_visualizer_requires_audio_but_asset_does_not(self) -> None:
        visualizer = OverlayLayer(
            id="viz", name="Wave", kind="visualizer", visualizer=VisualizerSpec(style="waveform")
        )
        result = validate_scene_sources(OverlayScene((visualizer,)), audio_available=False)
        self.assertFalse(result.ok)
        self.assertIn("exige uma faixa de áudio", result.errors[0])
        self.assertTrue(has_visualizer(result.scene))
        self.assertFalse(has_assets(result.scene))

    def test_existing_png_and_audio_pass(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "character.png"
            path.write_bytes(b"preview fixture")
            scene = OverlayScene((make_asset_layer(str(path), layer_id="asset"),))
            result = validate_scene_sources(scene, audio_available=False)
            self.assertTrue(result.ok)
            self.assertTrue(has_assets(scene))
            self.assertIn("1 PNG/GIF", summary(scene))


if __name__ == "__main__":
    unittest.main()
