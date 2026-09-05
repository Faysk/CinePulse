from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.gpu_compositor import OverlayLayer
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState
from cinepulse.ui.composer_view import (
    _default_export_path,
    _default_project_path,
    _snapshot_state,
    _studio_source_path,
)


class DummyVar:
    def __init__(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


class DummyStudio:
    def __init__(self, source: str = "") -> None:
        self.source = DummyVar(source)


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

    def test_empty_source_has_no_source_path(self) -> None:
        self.assertIsNone(_studio_source_path(DummyStudio("   ")))

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
