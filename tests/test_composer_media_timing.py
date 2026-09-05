from __future__ import annotations

import json
import unittest
from unittest import mock

from cinepulse.composer_media import media_info_from_probe, playback_position, probe_composer_media
from cinepulse.gpu_compositor import OverlayLayer


class ComposerMediaTimingInferenceTests(unittest.TestCase):
    def test_missing_nb_frames_is_derived_from_duration_and_rate(self) -> None:
        info = media_info_from_probe(
            "animated.webp",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "webp",
                        "width": 512,
                        "height": 512,
                        "pix_fmt": "rgba",
                        "avg_frame_rate": "30/1",
                        "duration": "2.0",
                    }
                ],
                "format": {"duration": "2.0"},
            },
        )
        self.assertEqual(60, info.frame_count)
        self.assertTrue(info.animated)
        self.assertFalse(info.timing_exact)
        layer = OverlayLayer("animated.webp", "webp", loop=True)
        position = playback_position(layer, info, project_time=1.5)
        self.assertEqual(45, position.frame_index)

    def test_fractional_rate_rounding_does_not_drop_effective_last_frame(self) -> None:
        info = media_info_from_probe(
            "alpha.webm",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "vp9",
                        "width": 640,
                        "height": 360,
                        "pix_fmt": "yuva420p",
                        "avg_frame_rate": "30000/1001",
                        "duration": "10.01",
                    }
                ]
            },
        )
        self.assertEqual(round(10.01 * (30000 / 1001)), info.frame_count)
        self.assertGreater(info.frame_count, 1)

    def test_static_image_still_keeps_one_frame_contract(self) -> None:
        info = media_info_from_probe(
            "still.png",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "png",
                        "width": 100,
                        "height": 50,
                        "pix_fmt": "rgba",
                        "avg_frame_rate": "0/0",
                    }
                ]
            },
        )
        self.assertEqual(1, info.frame_count)
        self.assertFalse(info.animated)
        self.assertTrue(playback_position(OverlayLayer("still.png", "png", loop=False), info, project_time=99).active)

    def test_exact_vfr_timestamps_override_misleading_average_rate(self) -> None:
        info = media_info_from_probe(
            "delayed.gif",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "gif",
                        "width": 64,
                        "height": 64,
                        "pix_fmt": "bgra",
                        "avg_frame_rate": "30/1",
                        "duration": "0.6",
                        "nb_frames": "3",
                    }
                ],
                "format": {"duration": "0.6"},
                "frames": [
                    {"best_effort_timestamp_time": "3.000", "pkt_duration_time": "0.100"},
                    {"best_effort_timestamp_time": "3.100", "pkt_duration_time": "0.300"},
                    {"best_effort_timestamp_time": "3.400", "pkt_duration_time": "0.200"},
                ],
            },
        )
        self.assertTrue(info.timing_exact)
        self.assertEqual((0.0, 0.1, 0.4), info.frame_starts)
        self.assertAlmostEqual(0.6, info.duration, places=7)
        layer = OverlayLayer("delayed.gif", "gif", loop=True)
        self.assertEqual(0, playback_position(layer, info, project_time=0.099).frame_index)
        self.assertEqual(1, playback_position(layer, info, project_time=0.100).frame_index)
        self.assertEqual(1, playback_position(layer, info, project_time=0.399).frame_index)
        self.assertEqual(2, playback_position(layer, info, project_time=0.400).frame_index)
        wrapped = playback_position(layer, info, project_time=0.65)
        self.assertEqual(1, wrapped.loop_index)
        self.assertAlmostEqual(0.05, wrapped.local_time, places=7)
        self.assertEqual(0, wrapped.frame_index)

    def test_non_monotonic_frame_timestamps_fail_closed_to_cfr_inference(self) -> None:
        info = media_info_from_probe(
            "broken-timing.webp",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "webp",
                        "width": 64,
                        "height": 64,
                        "pix_fmt": "rgba",
                        "avg_frame_rate": "10/1",
                        "duration": "0.3",
                        "nb_frames": "3",
                    }
                ],
                "frames": [
                    {"best_effort_timestamp_time": "0.0", "pkt_duration_time": "0.1"},
                    {"best_effort_timestamp_time": "0.1", "pkt_duration_time": "0.1"},
                    {"best_effort_timestamp_time": "0.1", "pkt_duration_time": "0.1"},
                ],
            },
        )
        self.assertFalse(info.timing_exact)
        self.assertEqual((), info.frame_starts)
        self.assertEqual(3, info.frame_count)
        self.assertEqual(2, playback_position(OverlayLayer("broken-timing.webp", "webp"), info, project_time=0.25).frame_index)

    @staticmethod
    def _probe_payload() -> dict:
        return {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "gif",
                    "width": 16,
                    "height": 16,
                    "pix_fmt": "bgra",
                    "avg_frame_rate": "10/1",
                    "duration": "0.2",
                    "nb_frames": "2",
                }
            ],
            "format": {"duration": "0.2"},
            "frames": [
                {"best_effort_timestamp_time": "0.0", "pkt_duration_time": "0.1"},
                {"best_effort_timestamp_time": "0.1", "pkt_duration_time": "0.1"},
            ],
        }

    def test_probe_requests_compact_decoded_frame_timeline(self) -> None:
        completed = mock.Mock(returncode=0, stdout=json.dumps(self._probe_payload()), stderr="")
        with mock.patch("cinepulse.composer_media.subprocess.run", return_value=completed) as run:
            info = probe_composer_media("ffprobe", "clip.gif")
        command = run.call_args.args[0]
        self.assertIn("-show_frames", command)
        entries = command[command.index("-show_entries") + 1]
        self.assertIn("frame=best_effort_timestamp_time,pts_time,pkt_duration_time", entries)
        self.assertTrue(info.timing_exact)
        self.assertEqual((0.0, 0.1), info.frame_starts)

    def test_lightweight_probe_omits_frame_enumeration(self) -> None:
        payload = self._probe_payload()
        payload.pop("frames")
        completed = mock.Mock(returncode=0, stdout=json.dumps(payload), stderr="")
        with mock.patch("cinepulse.composer_media.subprocess.run", return_value=completed) as run:
            info = probe_composer_media("ffprobe", "clip.gif", exact_timing=False, timeout=15.0)
        command = run.call_args.args[0]
        self.assertNotIn("-show_frames", command)
        entries = command[command.index("-show_entries") + 1]
        self.assertNotIn("frame=", entries)
        self.assertFalse(info.timing_exact)
        self.assertEqual(2, info.frame_count)


if __name__ == "__main__":
    unittest.main()
