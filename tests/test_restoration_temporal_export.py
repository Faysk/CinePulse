from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from cinepulse.restoration_inpaint import TemporalReconstructionPolicy
from cinepulse.restoration_overlay import OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPlan
from cinepulse.restoration_temporal_export import (
    PreviewVideoGeometry,
    _parse_rate,
    build_temporal_encoder_command,
    probe_preview_geometry,
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
        self.assertFalse(geometry.suspected_vfr)

    def test_geometry_exposes_frame_bound_duration(self):
        geometry = PreviewVideoGeometry(
            width=1920, height=1080, fps=30000 / 1001,
            nominal_fps=30000 / 1001, frame_count=30,
        )
        self.assertAlmostEqual(1.001, geometry.frame_bound_duration, places=12)

    def test_temporal_encoder_is_frame_bound_and_never_shortest(self):
        geometry = PreviewVideoGeometry(
            width=64, height=36, fps=4.0, nominal_fps=4.0,
            frame_count=4, duration=1.0, has_audio=True,
        )
        plan = PreviewRestorationPlan(evidence=(), regions=(), overlay_filter="", color_filter="")
        command = build_temporal_encoder_command(
            "ffmpeg", Path("source.mp4"), Path("out.mp4"), geometry, plan,
            video_codec="libx264", crf=16, preset="slow",
        )
        self.assertNotIn("-shortest", command)
        self.assertEqual("4", command[command.index("-frames:v") + 1])
        audio_index = command.index("source.mp4")
        self.assertEqual(["-t", "1.000000", "-i"], command[audio_index - 3:audio_index])
        self.assertIn("1:a?", command)

    def test_geometry_rejects_inconsistent_audio_presence_and_count(self):
        with self.assertRaisesRegex(ValueError, "audio presence/count"):
            PreviewVideoGeometry(
                width=64,
                height=36,
                fps=4.0,
                nominal_fps=4.0,
                frame_count=4,
                duration=1.0,
                has_audio=True,
                audio_stream_count=0,
            )

    def test_temporal_encoder_omits_audio_input_for_silent_source(self):
        geometry = PreviewVideoGeometry(
            width=64, height=36, fps=4.0, nominal_fps=4.0,
            frame_count=4, duration=1.0, has_audio=False,
        )
        plan = PreviewRestorationPlan(evidence=(), regions=(), overlay_filter="", color_filter="")
        command = build_temporal_encoder_command(
            "ffmpeg", Path("source.mp4"), Path("out.mp4"), geometry, plan,
            video_codec="libx264", crf=16, preset="slow",
        )
        self.assertNotIn("source.mp4", command)
        self.assertIn("-an", command)
        self.assertNotIn("-shortest", command)

    def test_probe_reads_exact_frames_and_audio_presence(self):
        payload = {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 64,
                    "height": 36,
                    "avg_frame_rate": "30000/1001",
                    "r_frame_rate": "30000/1001",
                    "nb_read_frames": "30",
                    "duration": "1.001",
                },
                {"codec_type": "audio", "duration": "1.000"},
            ],
            "format": {"duration": "1.001"},
        }
        completed = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout=json.dumps(payload), stderr=""
        )
        with patch("cinepulse.restoration_temporal_export.subprocess.run", return_value=completed) as run:
            geometry = probe_preview_geometry("ffprobe", Path("source.mp4"))
        self.assertEqual(30, geometry.frame_count)
        self.assertTrue(geometry.has_audio)
        self.assertEqual(1, geometry.audio_stream_count)
        self.assertAlmostEqual(1.001, geometry.duration or 0.0, places=6)
        command = run.call_args.args[0]
        self.assertIn("-count_frames", command)
        self.assertIn("-show_streams", command)

    def test_geometry_flags_material_avg_nominal_rate_mismatch(self):
        geometry = PreviewVideoGeometry(width=1920, height=1080, fps=24.0, nominal_fps=30.0)
        self.assertTrue(geometry.suspected_vfr)

        fractional_cfr = PreviewVideoGeometry(
            width=1920,
            height=1080,
            fps=30000 / 1001,
            nominal_fps=30000 / 1001,
        )
        self.assertFalse(fractional_cfr.suspected_vfr)

    def test_temporal_working_set_is_bounded_by_window_plus_target_copy(self):
        geometry = PreviewVideoGeometry(width=7680, height=4320, fps=60.0)
        policy = TemporalReconstructionPolicy(radius=4)
        expected_frames = (2 * policy.radius + 1) + 3
        self.assertEqual(
            geometry.estimated_temporal_working_set(policy),
            geometry.frame_bytes * expected_frames,
        )
        self.assertLess(geometry.estimated_temporal_working_set(policy), 2 * 1024**3)

    def test_12k_default_temporal_window_exceeds_two_gib_guard(self):
        geometry = PreviewVideoGeometry(width=12288, height=6480, fps=120.0)
        policy = TemporalReconstructionPolicy(radius=4)
        self.assertGreater(geometry.estimated_temporal_working_set(policy), 2 * 1024**3)

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
