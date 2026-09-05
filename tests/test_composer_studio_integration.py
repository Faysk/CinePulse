from __future__ import annotations

import inspect
import unittest
from dataclasses import fields
from unittest.mock import patch

import cinepulse.studio as studio_module
from cinepulse.studio import RenderSettings, VideoOptimizerStudio


class ComposerStudioIntegrationTests(unittest.TestCase):
    def test_stable_render_settings_remain_composer_free(self) -> None:
        names = {field.name.lower() for field in fields(RenderSettings)}
        forbidden = {"composer", "layers", "overlay_layers", "visualizers", "tensor_rt", "tensorrt"}
        self.assertTrue(names.isdisjoint(forbidden))

    def test_preview_composer_has_explicit_desktop_entry(self) -> None:
        source = inspect.getsource(VideoOptimizerStudio._build_ui)
        self.assertIn("Overlay Composer • Preview", source)
        self.assertIn("command=self._show_overlay_composer", source)

    def test_entry_delegates_to_isolated_composer_window(self) -> None:
        dummy = object()
        with patch("cinepulse.ui.composer_view.show_overlay_composer") as show:
            VideoOptimizerStudio._show_overlay_composer(dummy)
        show.assert_called_once_with(dummy)

    def test_composer_import_is_lazy_not_stable_startup_dependency(self) -> None:
        method_source = inspect.getsource(VideoOptimizerStudio._show_overlay_composer)
        self.assertIn("from .ui.composer_view import show_overlay_composer", method_source)
        module_source = inspect.getsource(studio_module)
        top_level = module_source.split("class VideoOptimizerStudio", 1)[0]
        self.assertNotIn("composer_view", top_level)


if __name__ == "__main__":
    unittest.main()
