from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from cinepulse.frame_quality import FrameQualityPolicy, analyze_luma_sequence, analyze_timeline
from cinepulse.media_stage_adapter import MediaUnitContract
from cinepulse.quality_stage import media_quality_validator


class FrameQualityTests(unittest.TestCase):
    def test_black_frame_is_detected_by_signal_not_packet_size(self) -> None:
        frames = [
            np.full((8, 8), 40, dtype=np.uint8),
            np.zeros((8, 8), dtype=np.uint8),
            np.full((8, 8), 42, dtype=np.uint8),
        ]
        report = analyze_luma_sequence(frames)
        self.assertEqual((1,), report.black_frames)
        self.assertFalse(report.passed)

    def test_legitimate_static_scene_is_not_false_freeze(self) -> None:
        frames = [np.full((8, 8), 80, dtype=np.uint8) for _ in range(8)]
        report = analyze_luma_sequence(frames)
        self.assertEqual((), report.freeze_intervals)

    def test_freeze_inserted_between_motion_is_detected(self) -> None:
        values = [20, 40, 60, 60, 60, 60, 90]
        frames = [np.full((8, 8), value, dtype=np.uint8) for value in values]
        report = analyze_luma_sequence(frames)
        self.assertEqual(1, len(report.freeze_intervals))
        freeze = report.freeze_intervals[0]
        self.assertEqual(3, freeze.pairs)
        self.assertGreater(freeze.context_before, 2.5)
        self.assertGreater(freeze.context_after, 2.5)

    def test_timeline_detects_duplicate_and_gap(self) -> None:
        step = 1 / 120
        pts = [0.0, step, step, step * 3, step * 4]
        issues = analyze_timeline(pts, 120.0)
        self.assertEqual(["duplicate_or_reverse", "gap"], [issue.kind for issue in issues])

    def test_media_quality_validator_combines_structure_signal_and_timeline(self) -> None:
        contract = MediaUnitContract(1920, 1080, 60.0, codec="ffv1", pix_fmt="yuv420p", exact_frames=4)
        probe = {
            "streams": [{
                "codec_type": "video", "width": 1920, "height": 1080,
                "avg_frame_rate": "60/1", "codec_name": "ffv1", "pix_fmt": "yuv420p",
                "nb_read_frames": "4",
            }]
        }
        frames = [np.full((8, 8), value, dtype=np.uint8) for value in (30, 50, 70, 90)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "segment.mkv"
            path.write_bytes(b"media")
            with (
                patch("cinepulse.media_stage_adapter.probe_media_unit", return_value=probe),
                patch("cinepulse.quality_stage.inspect_video_frames", return_value=analyze_luma_sequence(frames)),
                patch("cinepulse.quality_stage.probe_frame_pts", return_value=[0, 1 / 60, 2 / 60, 3 / 60]),
            ):
                result = media_quality_validator(
                    ffprobe="ffprobe",
                    ffmpeg="ffmpeg",
                    contract=contract,
                )(path)
        self.assertTrue(result.passed)
        self.assertEqual([], result.details["timeline_issues"])

    def test_media_quality_validator_rejects_generic_black(self) -> None:
        contract = MediaUnitContract(1920, 1080, 60.0, exact_frames=3)
        probe = {
            "streams": [{
                "codec_type": "video", "width": 1920, "height": 1080,
                "avg_frame_rate": "60/1", "codec_name": "ffv1", "pix_fmt": "yuv420p",
                "nb_read_frames": "3",
            }]
        }
        report = analyze_luma_sequence([
            np.full((8, 8), 40, dtype=np.uint8),
            np.zeros((8, 8), dtype=np.uint8),
            np.full((8, 8), 50, dtype=np.uint8),
        ])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "segment.mkv"
            path.write_bytes(b"media")
            with (
                patch("cinepulse.media_stage_adapter.probe_media_unit", return_value=probe),
                patch("cinepulse.quality_stage.inspect_video_frames", return_value=report),
                patch("cinepulse.quality_stage.probe_frame_pts", return_value=[0, 1 / 60, 2 / 60]),
            ):
                result = media_quality_validator(
                    ffprobe="ffprobe",
                    ffmpeg="ffmpeg",
                    contract=contract,
                    policy=FrameQualityPolicy(),
                )(path)
        self.assertFalse(result.passed)
        self.assertIn("black_frames", result.details["quality_errors"])


if __name__ == "__main__":
    unittest.main()
