from __future__ import annotations

import unittest

from cinepulse.media_profile import ColorProfile, audio_codec_for_container


class MediaProfileTests(unittest.TestCase):
    def test_detects_hdr10(self) -> None:
        profile = ColorProfile.from_probe({"streams": [{
            "codec_type": "video", "pix_fmt": "yuv420p10le", "color_primaries": "bt2020",
            "color_transfer": "smpte2084", "color_space": "bt2020nc", "color_range": "tv",
        }]})
        self.assertTrue(profile.hdr)
        self.assertEqual(10, profile.bit_depth)
        self.assertIn("HDR10", profile.label)

    def test_bt2020_primaries_with_sdr_transfer_are_not_misclassified_as_hdr(self) -> None:
        profile = ColorProfile.from_probe({"streams": [{
            "codec_type": "video", "pix_fmt": "yuv420p10le", "color_primaries": "bt2020",
            "color_transfer": "bt709", "color_space": "bt2020nc", "color_range": "tv",
        }]})
        self.assertFalse(profile.hdr)
        self.assertIn("SDR", profile.label)

    def test_lossless_audio_is_container_aware(self) -> None:
        self.assertEqual(["-c:a", "flac"], audio_codec_for_container(".mkv", lossless=True))
        self.assertIn("aac", audio_codec_for_container(".mp4", lossless=True))

