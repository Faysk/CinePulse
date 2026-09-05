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

    def test_automatic_check_is_disclosed_in_privacy_contract(self) -> None:
        privacy = (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
        self.assertIn("verificação HTTPS curta", privacy)
        self.assertIn("User-Agent", privacy)
        self.assertIn("nenhum caminho local, mídia, projeto", privacy)

    def test_release_gates_model_default_github_updater(self) -> None:
        gate = (ROOT / "scripts" / "release_gate.py").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "final_audit.py").read_text(encoding="utf-8")
        self.assertIn('update_source = "signed-manifest+github-installed" if manifest_url else "github-release"', gate)
        self.assertIn('"github_release_update_contract_safe"', audit)
        self.assertIn('"update_policy_trusted_source"', audit)
        self.assertNotIn('update_channel={update_policy}', gate)

    def test_updater_documentation_records_bootstrap_boundary(self) -> None:
        text = (ROOT / "docs" / "ONE_CLICK_UPDATER.md").read_text(encoding="utf-8")
        self.assertIn("CinePulse 1.1.3 predates this automatic startup discovery", text)
        self.assertIn("one-click", text.lower())
        self.assertIn("CINEPULSE_SKIP_BOOTSTRAP=1", text)


if __name__ == "__main__":
    unittest.main()
