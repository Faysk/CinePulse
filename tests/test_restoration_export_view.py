from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from cinepulse.ui import ai_view, restoration_export_view


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


if __name__ == "__main__":
    unittest.main()
