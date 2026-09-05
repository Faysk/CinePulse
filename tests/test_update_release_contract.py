from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateReleaseContractTests(unittest.TestCase):
    def test_no_temporary_updater_helpers_ship(self) -> None:
        leftovers = []
        for root in (ROOT / ".github" / "workflows", ROOT / "scripts"):
            for path in root.glob("*_tmp*updat*"):
                leftovers.append(path.relative_to(ROOT).as_posix())
            for path in root.glob("_tmp-*updat*"):
                leftovers.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], sorted(set(leftovers)))

    def test_updater_documentation_records_bootstrap_boundary(self) -> None:
        text = (ROOT / "docs" / "ONE_CLICK_UPDATER.md").read_text(encoding="utf-8")
        self.assertIn("CinePulse 1.1.3 predates this automatic startup discovery", text)
        self.assertIn("one-click", text.lower())
        self.assertIn("CINEPULSE_SKIP_BOOTSTRAP=1", text)


if __name__ == "__main__":
    unittest.main()
