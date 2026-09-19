from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.composer_preflight import GIB, estimate_composer_resources, validate_composer_resources
from cinepulse.composer_profile import ComposerBaseProfile


class DiskUsage:
    def __init__(self, free: int) -> None:
        self.total = free * 2
        self.used = free
        self.free = free


def profile(*, still_image: bool = False) -> ComposerBaseProfile:
    return ComposerBaseProfile(
        1920,
        1080,
        30.0,
        10.0,
        "yuv420p",
        "bt709",
        "bt709",
        "bt709",
        "tv",
        still_image=still_image,
    )


class ComposerPreflightTests(unittest.TestCase):
    def test_estimate_accounts_for_atomic_visual_and_mux_outputs(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("cinepulse.composer_preflight.shutil.disk_usage", return_value=DiskUsage(100 * GIB)),
            patch("cinepulse.composer_preflight._available_ram_bytes", return_value=16 * GIB),
        ):
            estimate = estimate_composer_resources(profile(), Path(temporary))
        self.assertEqual(1920 * 1080 * 4, estimate.frame_bytes)
        self.assertGreater(estimate.required_free_disk_bytes, estimate.estimated_visual_master_bytes * 2)
        self.assertGreater(estimate.estimated_peak_ram_bytes, estimate.frame_bytes * 4)

    def test_still_background_uses_lower_but_nonzero_lossless_planning_floor(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("cinepulse.composer_preflight.shutil.disk_usage", return_value=DiskUsage(100 * GIB)),
            patch("cinepulse.composer_preflight._available_ram_bytes", return_value=16 * GIB),
        ):
            video = estimate_composer_resources(profile(), Path(temporary))
            still = estimate_composer_resources(profile(still_image=True), Path(temporary))
        self.assertGreater(still.estimated_visual_master_bytes, 0)
        self.assertLess(still.estimated_visual_master_bytes, video.estimated_visual_master_bytes)

    def test_insufficient_disk_fails_before_render(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("cinepulse.composer_preflight.shutil.disk_usage", return_value=DiskUsage(1)),
            patch("cinepulse.composer_preflight._available_ram_bytes", return_value=16 * GIB),
        ):
            with self.assertRaisesRegex(RuntimeError, "GiB livres"):
                validate_composer_resources(profile(), Path(temporary))

    def test_insufficient_ram_fails_before_render(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("cinepulse.composer_preflight.shutil.disk_usage", return_value=DiskUsage(100 * GIB)),
            patch("cinepulse.composer_preflight._available_ram_bytes", return_value=64 * 1024**2),
        ):
            with self.assertRaisesRegex(RuntimeError, "RAM disponível"):
                validate_composer_resources(profile(), Path(temporary))


if __name__ == "__main__":
    unittest.main()
