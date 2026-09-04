from __future__ import annotations

import unittest

from cinepulse.overlay_composer import (
    AssetSpec,
    LayerTransform,
    NormalizedRect,
    OverlayLayer,
    OverlayScene,
    OverlaySceneError,
    VisualizerSpec,
)
from cinepulse.overlay_ffmpeg import OverlayFfmpegError, build_overlay_ffmpeg_plan


class OverlayFfmpegTests(unittest.TestCase):
    def test_png_and_waveform_build_streaming_overlay_plan(self) -> None:
        image = OverlayLayer(
            id="asset-1",
            name="Character",
            kind="asset",
            z_index=10,
            transform=LayerTransform(NormalizedRect(0.70, 0.55, 0.20, 0.35), opacity=0.85),
            asset=AssetSpec("character.png", "png"),
        )
        waveform = OverlayLayer(
            id="viz-1",
            name="Wave",
            kind="visualizer",
            z_index=20,
            transform=LayerTransform(NormalizedRect(0.48, 0.84, 0.34, 0.07), opacity=0.60, preserve_aspect=False),
            visualizer=VisualizerSpec(style="waveform", color="#F0E0C0", sensitivity=1.25, focus="bass"),
        )
        plan = build_overlay_ffmpeg_plan(
            OverlayScene((waveform, image)),
            canvas_width=1920,
            canvas_height=1080,
            fps=60,
            first_asset_input_index=2,
            base_video_label="basev",
            audio_label="1:a",
        )
        self.assertEqual(plan.asset_inputs[0].input_index, 2)
        self.assertIn("-loop", plan.input_args)
        self.assertIn("character.png", plan.input_args)
        self.assertIn("scale=384:378", plan.filter_complex)
        self.assertIn("showwaves=s=653x76", plan.filter_complex)
        self.assertIn("lowpass=f=280", plan.filter_complex)
        self.assertIn("volume=1.25", plan.filter_complex)
        self.assertIn("aa=0.6", plan.filter_complex)
        self.assertIn("overlay=x=1344:y=594", plan.filter_complex)
        self.assertEqual(plan.output_label, "ov_mix_1")

    def test_gif_uses_stream_loop_and_speed_without_expanding_frames(self) -> None:
        gif = OverlayLayer(
            id="gif-1",
            name="Animated",
            kind="asset",
            transform=LayerTransform(NormalizedRect(0.75, 0.70, 0.20, 0.20)),
            asset=AssetSpec("character.gif", "gif", loop=True, speed=1.5),
        )
        plan = build_overlay_ffmpeg_plan(
            OverlayScene((gif,)),
            canvas_width=1280,
            canvas_height=720,
            fps=30,
            first_asset_input_index=1,
            base_video_label="0:v",
            audio_label=None,
        )
        self.assertEqual(plan.asset_inputs[0].args[:2], ("-stream_loop", "-1"))
        self.assertIn("setpts=PTS/1.5", plan.filter_complex)
        self.assertNotIn("showwaves", plan.filter_complex)

    def test_multiple_visualizers_split_audio_once(self) -> None:
        first = OverlayLayer(
            id="viz-a",
            name="Bars",
            kind="visualizer",
            z_index=10,
            visualizer=VisualizerSpec(style="bars"),
        )
        second = OverlayLayer(
            id="viz-b",
            name="Spectrum",
            kind="visualizer",
            z_index=20,
            visualizer=VisualizerSpec(style="spectrum"),
        )
        plan = build_overlay_ffmpeg_plan(
            OverlayScene((first, second)),
            canvas_width=640,
            canvas_height=360,
            fps=30,
            first_asset_input_index=1,
            base_video_label="0:v",
            audio_label="0:a",
        )
        self.assertIn("[0:a]asplit=2[ov_audio_0][ov_audio_1]", plan.filter_complex)
        self.assertIn("mode=bar", plan.filter_complex)
        self.assertIn("mode=line", plan.filter_complex)

    def test_visualizer_without_audio_is_blocked(self) -> None:
        layer = OverlayLayer(
            id="viz",
            name="Wave",
            kind="visualizer",
            visualizer=VisualizerSpec(style="waveform"),
        )
        with self.assertRaises(OverlayFfmpegError):
            build_overlay_ffmpeg_plan(
                OverlayScene((layer,)),
                canvas_width=640,
                canvas_height=360,
                fps=30,
                first_asset_input_index=1,
                base_video_label="0:v",
                audio_label=None,
            )

    def test_empty_scene_returns_base_label_without_filters(self) -> None:
        plan = build_overlay_ffmpeg_plan(
            OverlayScene(),
            canvas_width=1920,
            canvas_height=1080,
            fps=60,
            first_asset_input_index=1,
            base_video_label="scaled",
            audio_label=None,
        )
        self.assertEqual(plan.filter_complex, "")
        self.assertEqual(plan.output_label, "scaled")
        self.assertEqual(plan.asset_inputs, ())


if __name__ == "__main__":
    unittest.main()
