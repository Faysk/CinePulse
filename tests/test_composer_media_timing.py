from __future__ import annotations

import unittest

from cinepulse.composer_media import media_info_from_probe, playback_position
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


if __name__ == "__main__":
    unittest.main()
