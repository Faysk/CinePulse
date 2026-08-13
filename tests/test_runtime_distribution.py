from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.runtime_distribution import InstanceGuard, find_powershell, installation_mode


class RuntimeDistributionTests(unittest.TestCase):
    def test_installation_mode_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {"CINEPULSE_PORTABLE": ""}, clear=False):
                self.assertEqual(installation_mode(root), "installed")
                (root / ".cinepulse-portable").touch()
                self.assertEqual(installation_mode(root), "portable")

    def test_instance_guard_blocks_second_process_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            first = InstanceGuard(path)
            second = InstanceGuard(path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_instance_guard_recovers_stale_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps({"schema": 1, "pid": 99999999}), encoding="utf-8")
            guard = InstanceGuard(path)
            self.assertTrue(guard.acquire())
            guard.release()

    @patch("cinepulse.runtime_distribution.shutil.which")
    def test_powershell_resolver_prefers_pwsh(self, which) -> None:
        def resolve(name: str):
            if name in {"pwsh.exe", "pwsh"}:
                return "/fake/pwsh"
            if name in {"powershell.exe", "powershell"}:
                return "/fake/powershell"
            return None
        which.side_effect = resolve
        choice = find_powershell()
        self.assertTrue(choice.modern)
        self.assertIn("pwsh", choice.executable)


if __name__ == "__main__":
    unittest.main()
