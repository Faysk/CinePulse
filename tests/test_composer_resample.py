from __future__ import annotations

import unittest

import numpy as np

from cinepulse.composer_resample import resize_bilinear_rgba, rotate_bilinear_rgba


class ComposerResampleTests(unittest.TestCase):
    def test_identity_is_exact_copy(self) -> None:
        source = np.arange(4 * 3 * 4, dtype=np.uint8).reshape(3, 4, 4)
        resized = resize_bilinear_rgba(source, 4, 3)
        self.assertTrue(np.array_equal(source, resized))
        self.assertIsNot(source, resized)

    def test_bilinear_scale_generates_intermediate_values(self) -> None:
        source = np.zeros((1, 2, 4), dtype=np.uint8)
        source[0, 0] = (0, 0, 0, 255)
        source[0, 1] = (255, 255, 255, 255)
        resized = resize_bilinear_rgba(source, 4, 1)
        self.assertEqual((0, 64, 191, 255), tuple(int(v) for v in resized[0, :, 0]))

    def test_transparent_color_does_not_bleed_into_visible_edge(self) -> None:
        source = np.zeros((1, 2, 4), dtype=np.uint8)
        source[0, 0] = (255, 0, 0, 0)
        source[0, 1] = (0, 255, 0, 255)
        resized = resize_bilinear_rgba(source, 3, 1)
        middle = resized[0, 1]
        self.assertLessEqual(int(middle[0]), 1)
        self.assertGreaterEqual(int(middle[1]), 254)
        self.assertTrue(120 <= int(middle[3]) <= 135)

    def test_quarter_rotation_remains_lossless(self) -> None:
        source = np.zeros((2, 3, 4), dtype=np.uint8)
        source[0, 0] = (10, 20, 30, 255)
        rotated = rotate_bilinear_rgba(source, 90.0)
        expected = np.rot90(source, k=3)
        self.assertTrue(np.array_equal(expected, rotated))

    def test_arbitrary_rotation_uses_partial_alpha_edges(self) -> None:
        source = np.zeros((5, 5, 4), dtype=np.uint8)
        source[1:4, 1:4, :3] = 255
        source[1:4, 1:4, 3] = 255
        rotated = rotate_bilinear_rgba(source, 33.0)
        alpha = rotated[..., 3]
        self.assertGreater(int(alpha.max()), 0)
        self.assertTrue(bool(np.any((alpha > 0) & (alpha < 255))))

    def test_invalid_dtype_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            resize_bilinear_rgba(np.zeros((2, 2, 4), dtype=np.float32), 4, 4)
        with self.assertRaises(ValueError):
            rotate_bilinear_rgba(np.zeros((2, 2, 4), dtype=np.float32), 45)


if __name__ == "__main__":
    unittest.main()
