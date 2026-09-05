from __future__ import annotations

import unittest

import numpy as np

from cinepulse.composer_runtime import (
    AudioFrameFeatures,
    ComposerFrameInputs,
    alpha_over,
    render_composer_frame,
    transform_overlay,
)
from cinepulse.gpu_compositor import OverlayLayer
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState, ReactiveFrameState, VisualizerLayer


class ComposerRuntimeTests(unittest.TestCase):
    def test_alpha_over_transparent_red_on_opaque_blue(self) -> None:
        base = np.zeros((2, 2, 4), dtype=np.uint8)
        base[..., 2] = 255
        base[..., 3] = 255
        overlay = np.zeros((1, 1, 4), dtype=np.uint8)
        overlay[0, 0] = (255, 0, 0, 128)
        alpha_over(base, overlay, 0, 0)
        self.assertEqual(255, int(base[0, 0, 3]))
        self.assertTrue(126 <= int(base[0, 0, 0]) <= 129)
        self.assertTrue(126 <= int(base[0, 0, 2]) <= 129)

    def test_transform_quarter_rotation_and_center_are_deterministic(self) -> None:
        source = np.zeros((2, 4, 4), dtype=np.uint8)
        source[..., 3] = 255
        source[0, 0, :3] = (255, 0, 0)
        state = ReactiveFrameState(0.5, 0.5, 1.0, 1.0, 90.0, 0.0)
        transformed, left, top = transform_overlay(source, state, 20, 10)
        self.assertEqual((4, 2), transformed.shape[:2])
        self.assertEqual((9, 3), (left, top))
        self.assertTrue(np.array_equal(transformed[0, -1, :3], np.array((255, 0, 0), dtype=np.uint8)))

    def test_render_respects_z_order(self) -> None:
        base = np.zeros((8, 8, 3), dtype=np.uint8)
        red = np.zeros((2, 2, 4), dtype=np.uint8); red[..., 0] = 255; red[..., 3] = 255
        green = np.zeros((2, 2, 4), dtype=np.uint8); green[..., 1] = 255; green[..., 3] = 255
        state = OverlayComposerState([
            ComposerItem("front", media=OverlayLayer("green.png", "png", z_order=2)),
            ComposerItem("back", media=OverlayLayer("red.png", "png", z_order=1)),
        ])
        frame = render_composer_frame(
            base,
            state,
            ComposerFrameInputs(0.0, {"back": red, "front": green}, {}),
        )
        center = frame[4, 4]
        self.assertEqual((0, 255, 0, 255), tuple(int(v) for v in center))

    def test_missing_media_frame_is_treated_as_inactive(self) -> None:
        base = np.full((6, 6, 3), 23, dtype=np.uint8)
        state = OverlayComposerState([ComposerItem("media", media=OverlayLayer("a.gif", "gif"))])
        rendered = render_composer_frame(base, state, ComposerFrameInputs(2.0, {}, {}))
        self.assertTrue(np.array_equal(rendered[..., :3], base))
        self.assertTrue(np.all(rendered[..., 3] == 255))

    def test_stem_binding_falls_back_to_master_features(self) -> None:
        base = np.zeros((32, 32, 3), dtype=np.uint8)
        layer = VisualizerLayer("spectrum", binding="drums", bars=8)
        state = OverlayComposerState([ComposerItem("viz", visualizer=layer)])
        hot = AudioFrameFeatures(rms=1.0, onset=1.0, band_energy=1.0, values=(1.0,) * 8)
        rendered = render_composer_frame(base, state, ComposerFrameInputs(0.0, {}, {"master": hot}))
        self.assertGreater(int(rendered[..., 3].min()), 0)
        self.assertGreater(int(rendered[..., :3].max()), 0)

    def test_invalid_base_or_overlay_dtype_fails_closed(self) -> None:
        state = OverlayComposerState()
        with self.assertRaises(ValueError):
            render_composer_frame(np.zeros((4, 4, 3), dtype=np.float32), state, ComposerFrameInputs(0.0, {}, {}))
        base = np.zeros((4, 4, 4), dtype=np.uint8)
        with self.assertRaises(ValueError):
            alpha_over(base, np.zeros((1, 1, 4), dtype=np.float32), 0, 0)


if __name__ == "__main__":
    unittest.main()
