from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.rife_engine import SAFE_RUNNER_MODULE, RifePaths, build_command, target_frame_count


class RifeEngineTests(unittest.TestCase):
    def test_target_count_is_deterministic(self) -> None:
        self.assertEqual(120, target_frame_count(2.0, 60))
        self.assertEqual(2, target_frame_count(0, 60))

    def test_command_routes_through_safe_runner_and_selected_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "rife.exe"
            executable.write_bytes(b"exe")
            model = root / "model"
            model.mkdir()
            command = build_command(RifePaths(executable, model), root / "in", root / "out", 60, use_cpu=True)
            self.assertEqual("-m", command[1])
            self.assertEqual(SAFE_RUNNER_MODULE, command[2])
            self.assertEqual("cpu", command[command.index("--device") + 1])
            self.assertEqual("60", command[command.index("--frames") + 1])
            self.assertNotIn("-n", command)

    def test_gpu_mode_is_delegated_to_safe_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "rife.exe"
            executable.write_bytes(b"exe")
            model = root / "model"
            model.mkdir()
            command = build_command(RifePaths(executable, model), root / "in", root / "out", 60, use_cpu=False)
            self.assertEqual("gpu", command[command.index("--device") + 1])
            self.assertNotIn("-g", command)


if __name__ == "__main__":
    unittest.main()
