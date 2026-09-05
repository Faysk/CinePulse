from __future__ import annotations

import unittest

import numpy as np

from cinepulse.restoration_inpaint import TemporalReconstructionPolicy
from cinepulse.restoration_overlay import OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPlan
from cinepulse.restoration_temporal_export import (
    PreviewVideoGeometry,
    _parse_rate,
    reconstruct_window_target,
)


class TemporalPreviewExportTests(unittest.TestCase):
    def test_parse_fractional_rate(self):
        self.assertAlmostEqual(_parse_rate("30000/1001"), 29.97002997, places=6)
        self.assertEqual(_parse_rate("60"), 60.0)
        with self.assertRaises(ValueError):
            _parse_rate("0/0")

    def test_geometry_reports_rgb24_frame_bytes(self):
        geometry = PreviewVideoGeometry(width=1920, height=1080, fps=60.0)
        self.assertEqual(geometry.frame_bytes, 1920 * 1080 * 3)

    def test_window_reconstruction_does_not_copy_persistent_overlay(self):
        frames = []
        for index in range(5):
            frame = np.full((20, 30, 3), 40 + index, dtype=np.uint8)
            frame[6:14, 10:20] = 250
            frames.append(frame)
        region = OverlayRegion(10 / 30, 6 / 20, 10 / 30, 8 / 20, kind="text", confidence=0.95)
        plan = PreviewRestorationPlan(
            evidence=(),
            regions=(region,),
            overlay_filter="delogo=x=10:y=6:w=10:h=8",
            color_filter="",
        )
        restored, applied, fallback = reconstruct_window_target(
            frames,
            target_index=2,
            plan=plan,
            policy=TemporalReconstructionPolicy(radius=2, minimum_donors=2, feather_pixels=0),
        )

        self.assertEqual(applied, 1)
        self.assertEqual(fallback, 0)
        self.assertFalse(np.array_equal(restored[10, 15], np.array([250, 250, 250], dtype=np.uint8)))
        self.assertLess(int(restored[10, 15, 0]), 100)


if __name__ == "__main__":
    unittest.main()
