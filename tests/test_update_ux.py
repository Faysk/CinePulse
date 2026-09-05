from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class UpdateUxContractTests(unittest.TestCase):
    @staticmethod
    def text(relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8", errors="replace")

    def test_startup_check_is_delayed_non_blocking_and_silent(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        self.assertIn("self._schedule(1200, self._startup_update_check)", studio)
        self.assertIn("self._check_updates(silent=True)", studio)
        self.assertIn("threading.Thread(target=worker, daemon=True).start()", studio)
        self.assertIn('if silent and phase == "check":', studio)
        self.assertIn("Verificação automática de atualização indisponível", studio)

    def test_new_release_exposes_prominent_update_cta(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        self.assertIn("self.header_update_button = ttk.Button(", studio)
        self.assertIn('label = f"Atualizar v{info.version}"', studio)
        self.assertIn("self.header_update_button.pack(", studio)
        self.assertIn("self._available_update = info", studio)
        self.assertIn('primary=("Atualizar agora", self._apply_available_update)', studio)

    def test_click_downloads_verifies_hands_off_and_does_not_interrupt_work(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        manager = self.text("src/cinepulse/update_manager.py")
        self.assertIn("self._busy or self._queue_running or self._ai_installing", studio)
        self.assertIn("update_manager.stage(info)", studio)
        self.assertIn("update_manager.launch_staged(info, Path(staged), APP_DIR, os.getpid())", studio)
        self.assertIn("check_available(", studio)
        self.assertIn("check_github_release", manager)
        self.assertIn("DEFAULT_RELEASE_API", manager)
        self.assertIn("asset.get(\"digest\")", manager)

    def test_installed_mode_uses_msi_major_upgrade_without_bootstrap_race(self) -> None:
        manager = self.text("src/cinepulse/update_manager.py")
        wix = self.text("installer/wix/Product.wxs")
        self.assertIn('package_kind = "msi" if installation == "installed" else "portable"', manager)
        self.assertIn("msiexec.exe", manager)
        self.assertIn("CINEPULSE_SKIP_BOOTSTRAP=1", manager)
        self.assertIn("<MajorUpgrade", wix)
        self.assertIn('UpgradeCode="5E804E94-E00A-47DF-A22A-85AF39D46586"', wix)

    def test_portable_update_keeps_existing_transactional_applier(self) -> None:
        manager = self.text("src/cinepulse/update_manager.py")
        self.assertIn('pending = runtime / "pending-update.json"', manager)
        self.assertIn('launcher = root / "CinePulse.cmd"', manager)
        self.assertIn("A atualização não passou na verificação SHA-256", manager)


if __name__ == "__main__":
    unittest.main()
