from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_compositor import OverlayLayer
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState
from cinepulse.ui.composer_view import (
    _default_export_path,
    _default_project_path,
    _snapshot_state,
    _studio_audio_path,
    _studio_output_size,
    _studio_source_path,
    show_overlay_composer,
)


class DummyVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class DummyStudio:
    def __init__(self, source: str = "", *, video: str = "", audio: str = "", resolution: str = "") -> None:
        self.source = DummyVar(source)
        self.video = DummyVar(video)
        self.audio = DummyVar(audio)
        self.resolution = DummyVar(resolution)


class ComposerViewHelpersTests(unittest.TestCase):
    def test_source_and_default_paths_are_source_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "clip.final.mp4"
            studio = DummyStudio(str(source))
            self.assertEqual(source, _studio_source_path(studio))
            self.assertEqual(
                source.with_suffix(".mp4.cinepulse-composer.json"),
                _default_project_path(studio),
            )
            self.assertEqual(
                source.with_name("clip.final-composer-reference.mkv"),
                _default_export_path(source),
            )


    def test_real_studio_video_and_audio_variables_are_supported(self) -> None:
        studio = DummyStudio(video="movie.mp4", audio="song.flac", resolution="4K UHD")
        self.assertEqual(Path("movie.mp4"), _studio_source_path(studio))
        self.assertEqual(Path("song.flac"), _studio_audio_path(studio))
        self.assertEqual((3840, 2160), _studio_output_size(studio))

    def test_empty_source_has_no_source_path(self) -> None:
        self.assertIsNone(_studio_source_path(DummyStudio("   ")))

    def test_default_composer_ui_is_direct_manipulation_not_coordinate_form(self) -> None:
        source = inspect.getsource(show_overlay_composer)
        self.assertIn("Escolher fundo", source)
        self.assertIn("+ GIF / imagem", source)
        self.assertIn("Arraste para mover", source)
        self.assertIn("<B1-Motion>", source)
        self.assertIn("Música automática", source)
        self.assertIn("_overlay_composer_export_done", source)
        self.assertIn("daemon=False", source)
        self.assertIn("closing_after_export", source)
        self.assertNotIn('text="Áudio / stems"', source)

    def test_export_snapshot_is_detached_from_editor_mutations(self) -> None:
        original = OverlayComposerState(
            [
                ComposerItem(
                    "logo",
                    media=OverlayLayer("logo.png", "png", opacity=0.75),
                )
            ]
        )
        snapshot = _snapshot_state(original)
        original.items[0] = ComposerItem(
            "logo",
            media=OverlayLayer("logo.png", "png", opacity=0.25),
            enabled=False,
        )
        self.assertIsNot(snapshot, original)
        self.assertEqual(0.75, snapshot.items[0].media.opacity)  # type: ignore[union-attr]
        self.assertTrue(snapshot.items[0].enabled)
        self.assertEqual((), original.ordered())
        self.assertEqual(1, len(snapshot.ordered()))


if __name__ == "__main__":
    unittest.main()
