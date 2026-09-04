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
            if __import__("os").name == "nt":
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.release()
                self.assertTrue(second.acquire())
                second.release()
            else:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.release()
                self.assertTrue(second.acquire())
                second.release()

    def test_file_guard_recovers_dead_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps({"schema": 1, "pid": 99999999}), encoding="utf-8")
            guard = InstanceGuard(path)
            with patch("cinepulse.runtime_distribution.process_alive", return_value=False):
                self.assertTrue(guard._acquire_file_lock())
            self.assertTrue(list(Path(directory).glob("instance.json.stale-*")))
            guard.release()

    def test_file_guard_recovers_pid_reuse_by_start_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(
                json.dumps({
                    "schema": 2,
                    "pid": 4242,
                    "process_start": "old-process",
                    "nonce": "old-owner",
                }),
                encoding="utf-8",
            )
            guard = InstanceGuard(path)
            with (
                patch("cinepulse.runtime_distribution.process_alive", return_value=True),
                patch("cinepulse.runtime_distribution.process_start_token", return_value="reused-pid"),
            ):
                self.assertTrue(guard._acquire_file_lock())
            current = json.loads(path.read_text(encoding="utf-8"))
            self.assertNotEqual(current["nonce"], "old-owner")
            guard.release()

    def test_file_guard_release_does_not_delete_foreign_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            guard = InstanceGuard(path)
            with patch("cinepulse.runtime_distribution.process_start_token", return_value="self-token"):
                self.assertTrue(guard._acquire_file_lock())
            foreign = {
                "schema": 2,
                "pid": 999,
                "process_start": "foreign",
                "nonce": "foreign-owner",
            }
            path.write_text(json.dumps(foreign), encoding="utf-8")
            guard.release()
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["nonce"], "foreign-owner")

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
