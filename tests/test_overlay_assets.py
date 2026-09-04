from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from cinepulse.overlay_assets import AssetFrameCache, AssetFrameKey, OverlayAssetError, effective_asset_time


class OverlayAssetTests(unittest.TestCase):
    def test_looping_gif_time_wraps_without_expanding_timeline(self) -> None:
        self.assertAlmostEqual(effective_asset_time(13.25, duration=4.0, speed=1.0, loop=True), 1.25)
        self.assertAlmostEqual(effective_asset_time(5.0, duration=4.0, speed=2.0, loop=True), 2.0)

    def test_non_looping_asset_clamps_to_last_frame_time(self) -> None:
        value = effective_asset_time(99.0, duration=3.0, speed=1.0, loop=False)
        self.assertGreaterEqual(value, 2.998)
        self.assertLess(value, 3.0)

    def test_invalid_speed_is_rejected(self) -> None:
        with self.assertRaises(OverlayAssetError):
            effective_asset_time(1.0, duration=2.0, speed=0.0, loop=True)

    def test_frame_cache_is_bounded_and_returns_copy(self) -> None:
        cache = AssetFrameCache(max_entries=2)
        frame = np.zeros((2, 2, 4), dtype=np.uint8)
        keys = [
            AssetFrameKey(f"asset-{index}", index, index + 1, 2, 2, index, True)
            for index in range(3)
        ]
        cache.put(keys[0], frame)
        cache.put(keys[1], frame + 1)
        returned = cache.get(keys[0])
        assert returned is not None
        returned[:] = 99
        self.assertFalse(np.all(cache.get(keys[0]) == 99))
        cache.put(keys[2], frame + 2)
        self.assertIsNone(cache.get(keys[1]))
        self.assertIsNotNone(cache.get(keys[0]))
        self.assertIsNotNone(cache.get(keys[2]))


if __name__ == "__main__":
    unittest.main()
