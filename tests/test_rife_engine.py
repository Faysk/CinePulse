from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.rife_engine import RifePaths, build_command, target_frame_count


class RifeEngineTests(unittest.TestCase):
    def test_target_count_is_deterministic(self) -> None:
        self.assertEqual(120, target_frame_count(2.0, 60))
        self.assertEqual(2, target_frame_count(0, 60))

    def test_command_uses_selected_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "rife.exe"
            executable.write_bytes(b"exe")
            model = root / "model"
            model.mkdir()
            command = build_command(RifePaths(executable, model), root / "in", root / "out", 60, use_cpu=True)
            self.assertEqual("-1", command[command.index("-g") + 1])
            self.assertEqual("60", command[command.index("-n") + 1])

    def test_gpu_mode_lets_ncnn_choose_high_performance_device(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "rife.exe"
            executable.write_bytes(b"exe")
            model = root / "model"
            model.mkdir()
            command = build_command(RifePaths(executable, model), root / "in", root / "out", 60, use_cpu=False)
            self.assertNotIn("-g", command)
