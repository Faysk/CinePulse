from __future__ import annotations

import unittest

import numpy as np

from cinepulse.ui.preview import demo_background, effect_thumbnail, to_ppm_bytes, visual_preview


class UiPreviewTests(unittest.TestCase):
    def test_demo_background_is_deterministic_rgb(self):
        first = demo_background(320, 180)
        second = demo_background(320, 180)
        self.assertEqual(first.shape, (180, 320, 3))
        self.assertEqual(first.dtype, np.uint8)
        self.assertTrue(np.array_equal(first, second))

    def test_effect_thumbnail_uses_real_vfx_and_changes_pixels(self):
        base = demo_background(160, 90)
        thumb = effect_thumbnail("Aurora", "#42D8FF", 160, 90)
        self.assertEqual(thumb.shape, base.shape)
        self.assertGreater(float(np.mean(np.abs(thumb.astype(np.int16) - base.astype(np.int16)))), 0.2)

    def test_visual_preview_without_effects_preserves_background(self):
        base = demo_background(320, 180)
        result = visual_preview(set(), "#42D8FF", 1.0, 0.65, base_rgb=base, width=320, height=180)
        self.assertTrue(np.array_equal(base, result))

    def test_ppm_header_and_payload(self):
        image = np.zeros((2, 3, 3), dtype=np.uint8)
        payload = to_ppm_bytes(image)
        self.assertTrue(payload.startswith(b"P6\n3 2\n255\n"))
        self.assertEqual(len(payload.split(b"\n", 3)[3]), 18)


if __name__ == "__main__":
    unittest.main()
