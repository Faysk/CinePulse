from __future__ import annotations

import unittest

from cinepulse.composer_media import (
    media_info_from_probe,
    pixel_format_has_alpha,
    playback_position,
    validate_layer_media,
    validate_project_media,
)
from cinepulse.gpu_compositor import OverlayLayer


class ComposerMediaTests(unittest.TestCase):
    def test_alpha_pixel_formats_are_conservative(self) -> None:
        self.assertTrue(pixel_format_has_alpha("rgba"))
        self.assertTrue(pixel_format_has_alpha("yuva444p12le"))
        self.assertTrue(pixel_format_has_alpha("gbrap16le"))
        self.assertFalse(pixel_format_has_alpha("yuv420p"))
        self.assertFalse(pixel_format_has_alpha("rgb24"))

    def test_probe_payload_derives_timing_and_alpha(self) -> None:
        info = media_info_from_probe(
            "disc.webm",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "vp9",
                        "width": 640,
                        "height": 640,
                        "pix_fmt": "yuva420p",
                        "avg_frame_rate": "30/1",
                        "duration": "2.0",
                        "nb_frames": "60",
                    }
                ],
                "format": {"duration": "2.0"},
            },
        )
        self.assertEqual((640, 640), (info.width, info.height))
        self.assertAlmostEqual(30.0, info.fps)
        self.assertAlmostEqual(2.0, info.duration)
        self.assertEqual(60, info.frame_count)
        self.assertTrue(info.has_alpha)
        self.assertTrue(info.animated)

    def test_static_image_gets_one_frame_hold_contract(self) -> None:
        info = media_info_from_probe(
            "logo.png",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "png",
                        "width": 512,
                        "height": 256,
                        "pix_fmt": "rgba",
                        "avg_frame_rate": "0/0",
                    }
                ]
            },
        )
        self.assertEqual(1, info.frame_count)
        self.assertEqual(1.0, info.fps)
        self.assertEqual(1.0, info.duration)
        self.assertFalse(info.animated)
        layer = OverlayLayer("logo.png", "png", loop=False)
        at_hour = playback_position(layer, info, project_time=3600.0)
        self.assertTrue(at_hour.active)
        self.assertEqual(0, at_hour.frame_index)

    def test_looped_animation_wraps_deterministically(self) -> None:
        info = media_info_from_probe(
            "spin.gif",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "gif",
                        "width": 320,
                        "height": 320,
                        "pix_fmt": "bgra",
                        "avg_frame_rate": "10/1",
                        "duration": "2.0",
                        "nb_frames": "20",
                    }
                ]
            },
        )
        layer = OverlayLayer("spin.gif", "gif", loop=True)
        position = playback_position(layer, info, project_time=5.25, start_time=1.0)
        self.assertTrue(position.active)
        self.assertEqual(2, position.loop_index)
        self.assertAlmostEqual(0.25, position.local_time, places=6)
        self.assertEqual(2, position.frame_index)

    def test_non_looping_animation_stops_after_last_frame(self) -> None:
        info = media_info_from_probe(
            "intro.apng",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "apng",
                        "width": 400,
                        "height": 200,
                        "pix_fmt": "rgba",
                        "avg_frame_rate": "24/1",
                        "duration": "1.0",
                        "nb_frames": "24",
                    }
                ]
            },
        )
        layer = OverlayLayer("intro.apng", "apng", loop=False)
        self.assertTrue(playback_position(layer, info, project_time=0.99).active)
        ended = playback_position(layer, info, project_time=1.0)
        self.assertFalse(ended.active)
        self.assertEqual(23, ended.frame_index)

    def test_video_alpha_fails_closed_without_alpha_pixel_format(self) -> None:
        info = media_info_from_probe(
            "overlay.mp4",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "pix_fmt": "yuv420p",
                        "avg_frame_rate": "30/1",
                        "duration": "3",
                        "nb_frames": "90",
                    }
                ]
            },
        )
        layer = OverlayLayer("overlay.mp4", "video-alpha")
        errors = validate_layer_media(layer, info)
        self.assertIn("video-alpha layer has no alpha-capable pixel format", errors)

    def test_project_validation_labels_layer_index(self) -> None:
        first = media_info_from_probe(
            "a.webm",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 64,
                        "height": 64,
                        "pix_fmt": "yuv420p",
                        "avg_frame_rate": "30/1",
                        "duration": "1",
                        "nb_frames": "30",
                    }
                ]
            },
        )
        second = media_info_from_probe(
            "b.png",
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "width": 64,
                        "height": 64,
                        "pix_fmt": "rgba",
                    }
                ]
            },
        )
        errors = validate_project_media(
            [
                (OverlayLayer("a.webm", "video-alpha"), first),
                (OverlayLayer("b.png", "png"), second),
            ]
        )
        self.assertEqual(("layer 0: video-alpha layer has no alpha-capable pixel format",), errors)


if __name__ == "__main__":
    unittest.main()
