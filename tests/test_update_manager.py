from __future__ import annotations

import unittest

from cinepulse.update_manager import is_newer


class UpdateManagerTests(unittest.TestCase):
    def test_release_order(self) -> None:
        self.assertTrue(is_newer("1.0.0", "1.0.0-rc1"))
        self.assertTrue(is_newer("1.0.0-rc2", "1.0.0-beta4"))
        self.assertTrue(is_newer("0.9.0", "0.1.0-alpha.2"))
        self.assertFalse(is_newer("1.2.0", "1.2.0"))
        self.assertFalse(is_newer("1.1.9", "1.2.0"))


if __name__ == "__main__":
    unittest.main()
