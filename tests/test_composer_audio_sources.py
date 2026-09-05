from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_compositor import OverlayLayer
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState


class ComposerAudioSourceStateTests(unittest.TestCase):
    def test_schema_two_roundtrip_persists_named_audio_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "composer.json"
            state = OverlayComposerState(
                [ComposerItem("logo", media=OverlayLayer("logo.png", "png"))],
                audio_sources={"vocals": str(root / "vocals.wav"), "bass": str(root / "bass.flac")},
            )
            state.save(project)
            restored = OverlayComposerState.load(project)
            self.assertEqual(state.as_dict(), restored.as_dict())
            self.assertEqual(2, restored.as_dict()["schema"])
            self.assertTrue(str(restored.audio_sources["vocals"]).endswith("vocals.wav"))

    def test_legacy_schema_one_loads_with_empty_audio_map(self) -> None:
        restored = OverlayComposerState.from_dict(
            {
                "schema": 1,
                "items": [
                    {
                        "id": "logo",
                        "enabled": True,
                        "media": {"source": "logo.png", "kind": "png"},
                        "visualizer": None,
                    }
                ],
            }
        )
        self.assertEqual({}, restored.audio_sources)
        self.assertEqual(2, restored.as_dict()["schema"])

    def test_master_defaults_to_video_source_and_custom_master_overrides(self) -> None:
        state = OverlayComposerState()
        resolved = state.resolved_audio_sources("movie.mkv")
        self.assertEqual("movie.mkv", resolved["master"])
        state.set_audio_source("master", "song.flac")
        self.assertEqual("song.flac", state.resolved_audio_sources("movie.mkv")["master"])
        self.assertTrue(state.clear_audio_source("master"))
        self.assertEqual("movie.mkv", state.resolved_audio_sources("movie.mkv")["master"])

    def test_unknown_binding_and_empty_persisted_source_fail_closed(self) -> None:
        state = OverlayComposerState()
        with self.assertRaises(ValueError):
            state.set_audio_source("guitar", "guitar.wav")
        with self.assertRaises(ValueError):
            state.set_audio_source("vocals", "")
        with self.assertRaises(ValueError):
            OverlayComposerState.from_dict({"schema": 2, "items": [], "audio_sources": {"vocals": ""}})
        with self.assertRaises(ValueError):
            OverlayComposerState.from_dict({"schema": 2, "items": [], "audio_sources": {"vocals": None}})
        with self.assertRaises(ValueError):
            OverlayComposerState.from_dict({"schema": 2, "items": [], "audio_sources": {"guitar": "x.wav"}})


if __name__ == "__main__":
    unittest.main()
