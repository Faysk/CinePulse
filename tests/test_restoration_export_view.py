from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cinepulse.ui import ai_view, restoration_export_view
from cinepulse.ui.restoration_lab import source_identity


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class RestorationExportViewTests(unittest.TestCase):
    def test_ai_workspace_exposes_preview_export_panel(self) -> None:
        source = inspect.getsource(ai_view.build_ai_tab)
        self.assertIn("build_restoration_export_panel(studio, parent)", source)

    def test_export_surface_does_not_reference_stable_render_settings(self) -> None:
        source = inspect.getsource(restoration_export_view)
        self.assertNotIn("RenderSettings(", source)
        self.assertNotIn("studio._settings", source)
        self.assertNotIn("_render", source.lower())

    def test_default_output_is_separate_and_keeps_supported_container(self) -> None:
        source = Path("/video/source.mkv")
        output = restoration_export_view._default_output(source)
        self.assertEqual(output.name, "source-restaurado-preview.mkv")
        self.assertNotEqual(output, source)

    def test_unknown_container_falls_back_to_mp4(self) -> None:
        output = restoration_export_view._default_output(Path("source.avi"))
        self.assertEqual(output.suffix, ".mp4")

    def test_overlay_export_fails_closed_when_source_changed_after_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.mp4"
            source.write_bytes(b"analyzed-version")
            analyzed = source_identity(source)
            self.assertIsNotNone(analyzed)
            studio = SimpleNamespace(
                restoration_remove_overlays=_Var(True),
                _restoration_plan=SimpleNamespace(evidence=()),
                _restoration_plan_identity=analyzed,
            )
            source.write_bytes(b"replacement-video-with-new-bytes")
            with patch.object(restoration_export_view, "_source_size", return_value=(1280, 720)):
                with self.assertRaisesRegex(ValueError, "fonte mudou"):
                    restoration_export_view._build_export_plan(studio, str(source))


if __name__ == "__main__":
    unittest.main()
