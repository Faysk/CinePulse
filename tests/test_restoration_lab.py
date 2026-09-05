from __future__ import annotations

import unittest

import numpy as np

from cinepulse.restoration_overlay import OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPlan
from cinepulse.ui.restoration_lab import (
    RestorationUiState,
    analysis_summary,
    color_preview,
    overlay_boxes_preview,
)


class RestorationLabTests(unittest.TestCase):
    def test_preset_and_manual_override_build_controls(self):
        state = RestorationUiState(preset="faded", saturation=1.2)
        controls = state.controls()
        self.assertAlmostEqual(controls.contrast, 1.10)
        self.assertAlmostEqual(controls.saturation, 1.2)

    def test_neutral_preview_preserves_rgb(self):
        image = np.arange(27, dtype=np.uint8).reshape(3, 3, 3)
        result = color_preview(image, RestorationUiState().controls())
        self.assertTrue(np.array_equal(image, result))
        self.assertIsNot(image, result)

    def test_color_preview_changes_pixels_but_preserves_shape_and_dtype(self):
        image = np.full((8, 10, 3), 100, dtype=np.uint8)
        result = color_preview(image, RestorationUiState(preset="warm").controls())
        self.assertEqual(result.shape, image.shape)
        self.assertEqual(result.dtype, np.uint8)
        self.assertFalse(np.array_equal(image, result))

    def test_analysis_summary_is_conservative_without_plan(self):
        text = analysis_summary(None)
        self.assertIn("desligada", text)

    def test_overlay_boxes_only_mark_selected_regions(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        region = OverlayRegion(x=0.1, y=0.2, width=0.2, height=0.1)
        plan = PreviewRestorationPlan(evidence=(), regions=(region,), overlay_filter="delogo=x=1:y=1:w=2:h=2", color_filter="")
        result = overlay_boxes_preview(image, plan)
        self.assertEqual(result.shape, image.shape)
        self.assertGreater(int(result.sum()), 0)
        self.assertTrue(np.array_equal(result[0, 0], np.zeros(3, dtype=np.uint8)))

    def test_summary_reports_region_count(self):
        region = OverlayRegion(x=0.1, y=0.2, width=0.2, height=0.1)
        plan = PreviewRestorationPlan(evidence=(), regions=(region,), overlay_filter="x", color_filter="")
        self.assertIn("1 região segura", analysis_summary(plan))


if __name__ == "__main__":
    unittest.main()
