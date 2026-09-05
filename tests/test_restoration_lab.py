from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from cinepulse.restoration_overlay import OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPlan
from cinepulse.ui.restoration_lab import (
    RestorationUiState,
    analysis_summary,
    color_preview,
    overlay_boxes_preview,
    source_identity,
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

    def test_source_identity_changes_when_file_is_replaced_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "clip.mp4"
            source.write_bytes(b"first")
            before = source_identity(source)
            self.assertIsNotNone(before)
            source.write_bytes(b"second-version")
            after = source_identity(source)
            self.assertIsNotNone(after)
            self.assertNotEqual(before, after)
            self.assertEqual(after.size, len(b"second-version"))

    def test_source_identity_fails_closed_for_missing_source(self):
        self.assertIsNone(source_identity(Path("definitely-missing-cinepulse-preview.mp4")))


if __name__ == "__main__":
    unittest.main()
