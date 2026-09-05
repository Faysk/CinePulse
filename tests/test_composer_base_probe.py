from __future__ import annotations

import unittest

from cinepulse.composer_base_probe import base_profile_from_probe


class ComposerBaseProbeTests(unittest.TestCase):
    def payload(self, **changes):
        stream = {
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": "30000/1001",
            "r_frame_rate": "30000/1001",
            "pix_fmt": "yuv420p",
            "color_primaries": "bt709",
            "color_transfer": "bt709",
            "color_space": "bt709",
            "color_range": "tv",
            "duration": "2.5",
        }
        stream.update(changes)
        return {"streams": [stream], "format": {"duration": "2.5"}}

    def test_sdr_bt709_profile_is_supported(self) -> None:
        profile = base_profile_from_probe(self.payload())
        self.assertEqual((1920, 1080), (profile.width, profile.height))
        self.assertAlmostEqual(30000 / 1001, profile.fps)
        self.assertTrue(profile.reference_supported)

    def test_hdr_and_ten_bit_profiles_fail_closed(self) -> None:
        self.assertFalse(base_profile_from_probe(self.payload(pix_fmt="yuv420p10le")).reference_supported)
        self.assertFalse(base_profile_from_probe(self.payload(color_transfer="smpte2084", color_primaries="bt2020", color_space="bt2020nc")).reference_supported)

    def test_format_duration_fallback_is_used(self) -> None:
        payload = self.payload()
        payload["streams"][0]["duration"] = None
        payload["format"]["duration"] = "3.75"
        profile = base_profile_from_probe(payload)
        self.assertEqual(3.75, profile.duration)

    def test_missing_video_or_bad_rate_fails_validation(self) -> None:
        with self.assertRaises(ValueError):
            base_profile_from_probe({"streams": [], "format": {}})
        with self.assertRaises(ValueError):
            base_profile_from_probe(self.payload(avg_frame_rate="0/0", r_frame_rate="0/0"))


if __name__ == "__main__":
    unittest.main()
