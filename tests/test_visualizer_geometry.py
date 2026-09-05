from __future__ import annotations

import unittest

from cinepulse.visualizer_geometry import circular_bars, geometry_for, spectrum_bars, waveform_points


class VisualizerGeometryTests(unittest.TestCase):
    def test_waveform_is_bounded_and_spans_viewport(self) -> None:
        points = waveform_points((-10.0, 0.25, 0.75, 10.0), reaction=2.0)
        self.assertEqual(0.0, points[0].x)
        self.assertEqual(1.0, points[-1].x)
        self.assertTrue(all(0.0 <= point.x <= 1.0 and 0.0 <= point.y <= 1.0 for point in points))

    def test_waveform_empty_input_has_stable_minimum_geometry(self) -> None:
        points = waveform_points(())
        self.assertEqual(2, len(points))
        self.assertEqual((0.0, 1.0), (points[0].x, points[-1].x))

    def test_spectrum_bars_are_ordered_bounded_and_bottom_anchored(self) -> None:
        bars = spectrum_bars((0.0, 0.5, 1.0), reaction=1.5)
        self.assertEqual(3, len(bars))
        self.assertTrue(all(0.0 <= bar.x0 <= bar.x1 <= 1.0 for bar in bars))
        self.assertTrue(all(bar.y1 == 1.0 and 0.0 <= bar.y0 <= 1.0 for bar in bars))
        self.assertEqual(0.0, bars[0].amplitude)
        self.assertEqual(1.0, bars[-1].amplitude)

    def test_circular_zero_signal_is_a_ring(self) -> None:
        bars = circular_bars((0.0,) * 8, inner_radius=0.25, radial_span=0.2)
        self.assertEqual(8, len(bars))
        for bar in bars:
            self.assertAlmostEqual(bar.inner.x, bar.outer.x, places=9)
            self.assertAlmostEqual(bar.inner.y, bar.outer.y, places=9)
            self.assertEqual(0.0, bar.amplitude)

    def test_circular_full_signal_extends_symmetrically(self) -> None:
        bars = circular_bars((1.0,) * 8, inner_radius=0.20, radial_span=0.20)
        self.assertAlmostEqual(0.9, bars[0].outer.x, places=8)
        self.assertAlmostEqual(0.5, bars[0].outer.y, places=8)
        self.assertAlmostEqual(0.1, bars[4].outer.x, places=8)
        self.assertAlmostEqual(0.5, bars[4].outer.y, places=8)
        self.assertTrue(all(0.0 <= bar.outer.x <= 1.0 and 0.0 <= bar.outer.y <= 1.0 for bar in bars))

    def test_rotation_is_deterministic(self) -> None:
        base = circular_bars((1.0,) * 8, rotation_degrees=0.0)
        rotated = circular_bars((1.0,) * 8, rotation_degrees=90.0)
        self.assertAlmostEqual(base[0].outer.x, rotated[6].outer.x, places=8)
        self.assertAlmostEqual(base[0].outer.y, rotated[6].outer.y, places=8)

    def test_dispatcher_rejects_unknown_kind(self) -> None:
        self.assertEqual(2, len(geometry_for("waveform", (0.0, 1.0))))
        self.assertEqual(2, len(geometry_for("spectrum", (0.0, 1.0))))
        self.assertEqual(8, len(geometry_for("circular", (1.0,) * 8)))
        with self.assertRaises(ValueError):
            geometry_for("banana", (1.0,))


if __name__ == "__main__":
    unittest.main()
