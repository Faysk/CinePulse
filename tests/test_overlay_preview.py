from __future__ import annotations

import unittest

import numpy as np

from cinepulse.overlay_composer import (
    LayerTransform,
    NormalizedRect,
    OverlayLayer,
    OverlayScene,
    VisualizerSpec,
    make_asset_layer,
)
from cinepulse.overlay_preview import (
    AudioReactiveState,
    composite_rgba_at,
    render_scene_preview,
    render_visualizer_rgba,
    rotate_rgba_nearest,
)


class OverlayPreviewTests(unittest.TestCase):
    def test_alpha_composition_respects_position_and_opacity(self) -> None:
        base = np.zeros((10, 12, 3), dtype=np.uint8)
        overlay = np.zeros((4, 5, 4), dtype=np.uint8)
        overlay[..., :3] = (200, 100, 50)
        overlay[..., 3] = 255
        out = composite_rgba_at(base, overlay, x=3, y=2, opacity=0.5)
        self.assertTrue(np.all(out[:2] == 0))
        self.assertTrue(np.all(out[2:6, 3:8, 0] == 100))
        self.assertTrue(np.all(out[2:6, 3:8, 1] == 50))
        self.assertTrue(np.all(out[2:6, 3:8, 2] == 25))

    def test_partial_off_canvas_overlay_is_clipped_not_rejected(self) -> None:
        base = np.zeros((8, 8, 3), dtype=np.uint8)
        overlay = np.zeros((6, 6, 4), dtype=np.uint8)
        overlay[..., :3] = 255
        overlay[..., 3] = 255
        out = composite_rgba_at(base, overlay, x=-3, y=-2)
        self.assertEqual(int(np.count_nonzero(out[..., 0])), 12)

    def test_rotation_keeps_rgba_shape_and_transparency(self) -> None:
        overlay = np.zeros((9, 9, 4), dtype=np.uint8)
        overlay[4, :, :3] = 255
        overlay[4, :, 3] = 255
        rotated = rotate_rgba_nearest(overlay, 90)
        self.assertEqual(rotated.shape, overlay.shape)
        self.assertGreater(int(np.count_nonzero(rotated[:, 4, 3])), 5)

    def test_waveform_changes_with_audio_state(self) -> None:
        spec = VisualizerSpec(style="waveform", color="#FFFFFF", sensitivity=1.0)
        quiet = render_visualizer_rgba(160, 48, spec, AudioReactiveState((0.1, 0.1, 0.1), 0.1, 0.0, 0.2))
        loud = render_visualizer_rgba(160, 48, spec, AudioReactiveState((1.0, 0.8, 0.7), 1.0, 1.0, 0.2))
        quiet_rows = np.where(np.any(quiet[..., 3] > 0, axis=1))[0]
        loud_rows = np.where(np.any(loud[..., 3] > 0, axis=1))[0]
        self.assertGreater(np.ptp(loud_rows), np.ptp(quiet_rows))

    def test_bars_are_transparent_outside_drawn_area(self) -> None:
        spec = VisualizerSpec(style="bars", bars=16, color="#FF0000", secondary_color="#0000FF")
        frame = render_visualizer_rgba(160, 80, spec)
        self.assertEqual(frame.shape, (80, 160, 4))
        self.assertGreater(int(np.count_nonzero(frame[..., 3])), 0)
        self.assertGreater(int(np.count_nonzero(frame[..., 3] == 0)), 0)

    def test_spectrum_is_a_curve_not_filled_bar_columns(self) -> None:
        spec = VisualizerSpec(
            style="spectrum",
            color="#FF8844",
            secondary_color="#44AAFF",
            thickness=0.30,
            mirror=False,
        )
        frame = render_visualizer_rgba(
            240,
            90,
            spec,
            AudioReactiveState((0.85, 0.62, 0.44), 0.75, 0.30, 0.18),
        )
        alpha = frame[..., 3] > 0
        active_columns = np.where(np.any(alpha, axis=0))[0]
        self.assertGreater(len(active_columns), 220)
        # A line spectrum should remain sparse; filled bars would occupy a much
        # larger fraction of the 240x90 surface.
        self.assertLess(float(np.mean(alpha)), 0.22)

    def test_mirrored_spectrum_occupies_both_halves(self) -> None:
        spec = VisualizerSpec(
            style="spectrum",
            color="#FF0000",
            secondary_color="#0000FF",
            thickness=0.35,
            mirror=True,
        )
        frame = render_visualizer_rgba(
            220,
            100,
            spec,
            AudioReactiveState((0.9, 0.7, 0.5), 0.8, 0.4, 0.33),
        )
        alpha = frame[..., 3]
        self.assertGreater(int(np.count_nonzero(alpha[:50])), 0)
        self.assertGreater(int(np.count_nonzero(alpha[50:])), 0)
        colors = frame[alpha > 0, :3]
        # Horizontal gradient should expose more than a single RGB value.
        self.assertGreater(len(np.unique(colors, axis=0)), 8)

    def test_scene_composes_asset_and_visualizer_in_z_order(self) -> None:
        base = np.zeros((100, 200, 3), dtype=np.uint8)
        asset = make_asset_layer(
            "character.png",
            layer_id="asset-1",
            rect=NormalizedRect(0.70, 0.50, 0.20, 0.40),
            z_index=10,
        )
        visualizer = OverlayLayer(
            id="viz-1",
            name="Wave",
            kind="visualizer",
            z_index=20,
            transform=LayerTransform(NormalizedRect(0.45, 0.80, 0.40, 0.10), preserve_aspect=False),
            visualizer=VisualizerSpec(style="waveform", color="#FFFFFF"),
        )
        asset_frame = np.zeros((40, 40, 4), dtype=np.uint8)
        asset_frame[..., :3] = (100, 40, 20)
        asset_frame[..., 3] = 255
        scene = OverlayScene((visualizer, asset))
        out = render_scene_preview(base, scene, asset_frames={"asset-1": asset_frame})
        self.assertTrue(np.any(out[50:90, 140:180] != 0))
        self.assertTrue(np.any(out[80:90, 90:170] != 0))


if __name__ == "__main__":
    unittest.main()
