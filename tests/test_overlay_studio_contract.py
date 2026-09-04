from __future__ import annotations

import json
import unittest

from cinepulse.overlay_composer import OverlayScene, make_visualizer_layer
from cinepulse.studio import (
    ASPECT_LANDSCAPE,
    ENHANCE_NONE,
    FIT_CONTAIN,
    MODE_MUSIC,
    PROFILE_AUTO,
    VideoOptimizerStudio,
)


def legacy_settings_payload() -> dict:
    return {
        "mode": MODE_MUSIC,
        "video": "video.mp4",
        "audio": "music.wav",
        "output": "out.mp4",
        "resolution": "1080p Full HD",
        "fps": 60,
        "aspect": ASPECT_LANDSCAPE,
        "enhancement": ENHANCE_NONE,
        "fit_mode": FIT_CONTAIN,
        "use_cpu": True,
        "preserve_audio": True,
        "effects": [],
        "color": "#43D6FF",
        "intensity": 1.0,
        "occupancy": 0.5,
        "audio_focus": "Todos equilibrados",
        "reaction_smoothing": 0.8,
        "reaction_expression": 0.8,
        "auto_loop": False,
        "dynamic_sections": False,
        "section_dynamics": 0.7,
        "transition": "Corte seco — original",
        "transition_duration": 0.75,
        "preview_seconds": 10,
        "audio_mode": "Preservar dinâmica original",
        "interpolation": "Movimento suave — FFmpeg",
        "cpu_threads": 4,
        "minimum_free_gb": 10.0,
        "quality_check": True,
        "delivery_profile": PROFILE_AUTO,
    }


class OverlayStudioContractTests(unittest.TestCase):
    def test_legacy_queue_settings_get_empty_overlay_scene(self) -> None:
        settings = VideoOptimizerStudio._settings_from_dict(legacy_settings_payload())
        scene = OverlayScene.from_json(settings.overlay_scene_json)
        self.assertEqual(scene, OverlayScene())

    def test_persisted_overlay_scene_survives_settings_roundtrip(self) -> None:
        scene = OverlayScene((make_visualizer_layer(layer_id="viz", style="waveform"),))
        payload = legacy_settings_payload()
        payload["overlay_scene_json"] = scene.to_json()
        settings = VideoOptimizerStudio._settings_from_dict(payload)
        restored = OverlayScene.from_json(settings.overlay_scene_json)
        self.assertEqual(restored, scene)
        self.assertEqual(restored.fingerprint, scene.fingerprint)

    def test_unknown_future_fields_do_not_break_queue_restore(self) -> None:
        payload = legacy_settings_payload()
        payload["future_preview_field"] = {"some": "value"}
        settings = VideoOptimizerStudio._settings_from_dict(payload)
        self.assertEqual(settings.mode, MODE_MUSIC)
        self.assertEqual(OverlayScene.from_json(settings.overlay_scene_json), OverlayScene())

    def test_settings_from_dict_keeps_effects_as_set(self) -> None:
        payload = legacy_settings_payload()
        payload["effects"] = ["Aurora", "Pulso cinematográfico"]
        settings = VideoOptimizerStudio._settings_from_dict(payload)
        self.assertEqual(settings.effects, {"Aurora", "Pulso cinematográfico"})


if __name__ == "__main__":
    unittest.main()
