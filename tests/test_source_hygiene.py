from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SourceHygieneTests(unittest.TestCase):
    def test_runtime_payloads_are_not_in_source_tree(self) -> None:
        forbidden = [ROOT / "tools", ROOT / "config_video_optimizer_studio", ROOT / "temp_video_optimizer_studio"]
        self.assertEqual([], [str(path) for path in forbidden if path.exists()])

    def test_no_large_tracked_candidates(self) -> None:
        ignored = {".git", ".runtime", ".venv", "components", "data"}
        large = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in ignored for part in path.parts):
                continue
            if path.stat().st_size > 90 * 1024 * 1024:
                large.append(str(path.relative_to(ROOT)))
        self.assertEqual([], large)


if __name__ == "__main__":
    unittest.main()

