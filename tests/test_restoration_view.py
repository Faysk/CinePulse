from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from cinepulse.ui import ai_view, restoration_view


class RestorationViewTests(unittest.TestCase):
    def test_safe_size_probes_media_before_reading_video_dimensions(self) -> None:
        probe = {"streams": [{"codec_type": "video", "width": 3840, "height": 2160}]}
        with patch.object(restoration_view, "probe_media", return_value=probe) as probe_media:
            self.assertEqual(restoration_view._safe_size("clip.mp4"), (3840, 2160))
        probe_media.assert_called_once_with("clip.mp4")

    def test_safe_size_fails_closed_when_probe_is_invalid(self) -> None:
        with patch.object(restoration_view, "probe_media", side_effect=RuntimeError("bad source")):
            self.assertIsNone(restoration_view._safe_size("broken.mp4"))

    def test_ai_workspace_exposes_preview_restoration_panel(self) -> None:
        source = inspect.getsource(ai_view.build_ai_tab)
        self.assertIn("build_restoration_panel(studio, parent)", source)

    def test_restoration_surface_does_not_reference_render_settings(self) -> None:
        source = inspect.getsource(restoration_view)
        self.assertNotIn("RenderSettings(", source)
        self.assertNotIn("studio._settings", source)


if __name__ == "__main__":
    unittest.main()
