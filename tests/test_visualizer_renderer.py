from __future__ import annotations

import unittest

import numpy as np

from cinepulse.overlay_composer import VisualizerLayer, evaluate_visualizer_frame
from cinepulse.visualizer_renderer import VisualizerColor, render_visualizer_rgba


class VisualizerRendererTests(unittest.TestCase):
    def state(self, layer: VisualizerLayer):
        return evaluate_visualizer_frame(
            layer,
            time_seconds=0.0,
            rms=1.0,
            onset=1.0,
            band_energy=1.0,
        )

    def test_all_requested_shapes_render_rgba(self) -> None:
        for kind in ("waveform", "spectrum", "circular"):
            layer = VisualizerLayer(kind, bars=8, thickness=2.0)
            frame = render_visualizer_rgba(layer, (0.0, 0.25, 0.5, 0.75, 1.0, 0.75, 0.5, 0.25), self.state(layer), width=160, height=90)
            self.assertEqual((90, 160, 4), frame.shape)
            self.assertEqual(np.uint8, frame.dtype)
            self.assertGreater(int(frame[..., 3].max()), 0)

    def test_opacity_is_preserved_in_alpha_contract(self) -> None:
        layer = VisualizerLayer("waveform", opacity=0.25, thickness=1.0)
        frame = render_visualizer_rgba(layer, (0.0, 1.0), self.state(layer), width=64, height=64)
        self.assertEqual(round(255 * 0.25), int(frame[..., 3].max()))

    def test_color_is_exact_on_covered_pixels(self) -> None:
        layer = VisualizerLayer("spectrum", bars=8)
        frame = render_visualizer_rgba(
            layer,
            (1.0,) * 8,
            self.state(layer),
            width=80,
            height=80,
            color=VisualizerColor(12, 34, 56),
        )
        covered = frame[..., 3] > 0
        self.assertTrue(bool(np.any(covered)))
        self.assertTrue(bool(np.all(frame[covered, 0] == 12)))
        self.assertTrue(bool(np.all(frame[covered, 1] == 34)))
        self.assertTrue(bool(np.all(frame[covered, 2] == 56)))

    def test_zero_circular_signal_does_not_invent_energy(self) -> None:
        layer = VisualizerLayer("circular", bars=8)
        frame = render_visualizer_rgba(layer, (0.0,) * 8, self.state(layer), width=100, height=100)
        # A zero circular signal draws only the eight anchor points/ring starts,
        # not long radial energy bars.
        self.assertLess(int(np.count_nonzero(frame[..., 3])), 64)

    def test_render_is_deterministic(self) -> None:
        layer = VisualizerLayer("waveform", thickness=3.0, opacity=0.8)
        state = self.state(layer)
        first = render_visualizer_rgba(layer, (0.0, 0.5, 1.0, 0.5), state, width=96, height=54)
        second = render_visualizer_rgba(layer, (0.0, 0.5, 1.0, 0.5), state, width=96, height=54)
        self.assertTrue(np.array_equal(first, second))


if __name__ == "__main__":
    unittest.main()
