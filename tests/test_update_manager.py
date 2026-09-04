from __future__ import annotations

import unittest

from cinepulse.update_manager import UpdateInfo, _validated_update_info, is_newer, stage


class UpdateManagerTests(unittest.TestCase):
    def test_release_order(self) -> None:
        self.assertTrue(is_newer("1.0.0", "1.0.0-rc1"))
        self.assertTrue(is_newer("1.0.0-rc2", "1.0.0-beta4"))
        self.assertTrue(is_newer("0.9.0", "0.1.0-alpha.2"))
        self.assertFalse(is_newer("1.2.0", "1.2.0"))
        self.assertFalse(is_newer("1.1.9", "1.2.0"))

    def test_staging_boundary_accepts_normalized_valid_info(self) -> None:
        version, digest = _validated_update_info(
            UpdateInfo(" 1.1.1 ", "https://example.invalid/CinePulse.zip", "A" * 64)
        )
        self.assertEqual(version, "1.1.1")
        self.assertEqual(digest, "a" * 64)

    def test_stage_rejects_invalid_version_before_filesystem_or_network(self) -> None:
        with self.assertRaises(ValueError):
            stage(UpdateInfo("../1.1.1", "https://example.invalid/CinePulse.zip", "a" * 64))

    def test_stage_rejects_non_https_download_before_filesystem_or_network(self) -> None:
        with self.assertRaises(ValueError):
            stage(UpdateInfo("1.1.1", "http://example.invalid/CinePulse.zip", "a" * 64))

    def test_stage_rejects_invalid_sha_before_filesystem_or_network(self) -> None:
        with self.assertRaises(ValueError):
            stage(UpdateInfo("1.1.1", "https://example.invalid/CinePulse.zip", "not-a-sha"))


if __name__ == "__main__":
    unittest.main()
