from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateBootstrapContractTests(unittest.TestCase):
    def test_acceptance_docs_do_not_claim_retroactive_auto_update(self) -> None:
        docs = "\n".join(
            (ROOT / path).read_text(encoding="utf-8")
            for path in ("docs/ONE_CLICK_UPDATER.md", "docs/ONE_CLICK_UPDATER_ACCEPTANCE.md")
        )
        self.assertIn("1.1.3", docs)
        self.assertIn("first Stable release", docs)
        self.assertIn("bootstrap", docs.lower())


if __name__ == "__main__":
    unittest.main()
