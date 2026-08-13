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

    def test_processing_labels_do_not_claim_all_gpu(self) -> None:
        paths = [ROOT / "src" / "cinepulse" / "studio.py", ROOT / "src" / "cinepulse" / "ui"]
        text = []
        for path in paths:
            if path.is_file():
                text.append(path.read_text(encoding="utf-8"))
            else:
                text.extend(item.read_text(encoding="utf-8") for item in path.rglob("*.py"))
        self.assertNotIn("GPU automática", "\n".join(text))


if __name__ == "__main__":
    unittest.main()

