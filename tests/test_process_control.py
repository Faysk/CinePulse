from __future__ import annotations

import signal
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from cinepulse import process_control


class ProcessControlTests(unittest.TestCase):
    def test_posix_escalates_to_sigkill_when_sigterm_is_ignored(self) -> None:
        process = MagicMock(spec=subprocess.Popen)
        process.pid = 1234
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired(cmd="child", timeout=2)
        messages: list[str] = []
        with (
            patch.object(process_control.os, "name", "posix"),
            patch("cinepulse.process_control.os.getpgid", return_value=4321, create=True),
            patch("cinepulse.process_control.os.killpg", create=True) as killpg,
            patch("cinepulse.process_control._wait_for_exit", return_value=False),
        ):
            process_control.terminate_process_tree(process, messages.append, grace_seconds=0.01)
        self.assertEqual(
            [call.args for call in killpg.call_args_list],
            [(4321, signal.SIGTERM), (4321, signal.SIGKILL)],
        )
        self.assertTrue(any("SIGKILL" in message for message in messages))

    def test_posix_stops_after_clean_sigterm(self) -> None:
        process = MagicMock(spec=subprocess.Popen)
        process.pid = 1234
        process.poll.return_value = None
        with (
            patch.object(process_control.os, "name", "posix"),
            patch("cinepulse.process_control.os.getpgid", return_value=4321, create=True),
            patch("cinepulse.process_control.os.killpg", create=True) as killpg,
            patch("cinepulse.process_control._wait_for_exit", return_value=True),
        ):
            process_control.terminate_process_tree(process, grace_seconds=0.01)
        killpg.assert_called_once_with(4321, signal.SIGTERM)

    def test_direct_fallback_escalates_from_terminate_to_kill(self) -> None:
        process = MagicMock(spec=subprocess.Popen)
        process.pid = 1234
        process.poll.return_value = None
        with (
            patch.object(process_control.os, "name", "posix"),
            patch("cinepulse.process_control.os.getpgid", side_effect=OSError("no group"), create=True),
            patch("cinepulse.process_control._wait_for_exit", return_value=False),
        ):
            process_control.terminate_process_tree(process, grace_seconds=0.01)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
