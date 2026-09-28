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

    def test_portable_apply_consumes_the_same_descriptor_bytes_it_validates(self) -> None:
        applier = (ROOT / "installer" / "Apply-CinePulseUpdate.ps1").read_text(encoding="utf-8-sig")
        launcher = (ROOT / "installer" / "Start-CinePulse.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("[IO.File]::ReadAllBytes($PendingFile)", applier)
        self.assertIn("CINEPULSE_EXPECTED_PENDING_SHA256", applier)
        self.assertIn("ComputeHash($PendingBytes)", applier)
        self.assertIn("$PendingText | ConvertFrom-Json", applier)
        self.assertNotIn("Get-Content -LiteralPath $PendingFile -Raw | ConvertFrom-Json", applier)
        self.assertIn("Remove-Item Env:CINEPULSE_EXPECTED_PENDING_SHA256", launcher)


if __name__ == "__main__":
    unittest.main()
