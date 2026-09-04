from __future__ import annotations

import unittest

from cinepulse.overlay_composer import NormalizedRect, OverlayScene, make_asset_layer, make_visualizer_layer
from cinepulse.overlay_ffmpeg import build_overlay_ffmpeg_plan
from cinepulse.overlay_longform import assess_longform


class OverlayLongformTests(unittest.TestCase):
    def _scene(self) -> OverlayScene:
        return OverlayScene((
            make_asset_layer(
                "character.png",
                layer_id="png",
                rect=NormalizedRect(0.72, 0.48, 0.22, 0.40),
            ),
            make_asset_layer(
                "character.gif",
                layer_id="gif",
                media_kind="gif",
                rect=NormalizedRect(0.08, 0.12, 0.12, 0.20),
            ),
            make_visualizer_layer(
                layer_id="wave",
                style="waveform",
                rect=NormalizedRect(0.52, 0.84, 0.40, 0.075),
            ),
            make_visualizer_layer(
                layer_id="bars",
                style="bars",
                rect=NormalizedRect(0.08, 0.78, 0.32, 0.12),
            ),
        ))

    def test_two_hour_project_does_not_materialize_duration_scaled_frames(self) -> None:
        scene = self._scene()
        short = assess_longform(scene, 30.0)
        long = assess_longform(scene, 7200.0)
        self.assertTrue(short.streaming_safe)
        self.assertTrue(long.streaming_safe)
        self.assertEqual(long.materialized_frame_count, 0)
        self.assertEqual(long.duration_scaled_temp_bytes, 0)
        self.assertEqual(long.auxiliary_input_streams, short.auxiliary_input_streams)
        self.assertEqual(long.auxiliary_input_streams, 3)  # 2 assets + one shared visualizer audio read
        self.assertIn("2.00 h", long.summary)
        self.assertIn("sem sequência temporária por frame", long.summary)

    def test_ffmpeg_plan_has_stream_inputs_not_frame_sequence_expansion(self) -> None:
        scene = self._scene()
        plan = build_overlay_ffmpeg_plan(
            scene,
            canvas_width=1920,
            canvas_height=1080,
            fps=60,
            first_asset_input_index=3,
            base_video_label="base",
            audio_label="2:a",
        )
        joined = " ".join(plan.input_args) + " " + plan.filter_complex
        self.assertIn("-loop 1", " ".join(plan.input_args))
        self.assertIn("-stream_loop -1", " ".join(plan.input_args))
        self.assertIn("asplit=2", plan.filter_complex)
        for forbidden in ("frame%", "frame*.png", "frames/", "select=", "thumbnail="):
            self.assertNotIn(forbidden, joined)

    def test_long_gif_project_warns_about_repeated_decode_without_calling_it_temp_growth(self) -> None:
        assessment = assess_longform(self._scene(), 7200.0)
        self.assertTrue(any("GIF" in warning and "streaming" in warning for warning in assessment.warnings))
        self.assertEqual(assessment.duration_scaled_temp_bytes, 0)


if __name__ == "__main__":
    unittest.main()
