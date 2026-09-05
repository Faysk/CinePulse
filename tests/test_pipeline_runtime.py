from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cinepulse.pipeline_runtime import (
    BackgroundCommand,
    measure_resource_headroom,
    measure_scratch_write_mbps,
    vram_free_mb,
)


class FakeGpuSampler:
    def sample(self):
        return (
            SimpleNamespace(index=0, vram_free_mb=7424.0),
            SimpleNamespace(index=1, vram_free_mb=16384.0),
        )


class PipelineRuntimeTests(unittest.TestCase):
    def test_vram_probe_selects_requested_gpu(self) -> None:
        self.assertEqual(vram_free_mb(1, sampler=FakeGpuSampler()), 16384.0)
        self.assertEqual(vram_free_mb(0, sampler=FakeGpuSampler()), 7424.0)
        self.assertIsNone(vram_free_mb(2, sampler=FakeGpuSampler()))

    def test_scratch_probe_writes_flushes_and_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            speed, written = measure_scratch_write_mbps(root, size_mb=1, minimum_free_gb=0.0)
            self.assertIsNotNone(speed)
            self.assertGreater(speed or 0.0, 0.0)
            self.assertEqual(written, 1024 ** 2)
            self.assertFalse(any(root.glob("cinepulse-h4-write-*.probe")))

    def test_low_scratch_headroom_fails_closed_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake_usage = SimpleNamespace(total=10, used=9, free=1024)
            with patch("cinepulse.pipeline_runtime.shutil.disk_usage", return_value=fake_usage):
                speed, written = measure_scratch_write_mbps(root, size_mb=32, minimum_free_gb=1.0)
            self.assertIsNone(speed)
            self.assertEqual(written, 0)
            self.assertFalse(any(root.glob("cinepulse-h4-write-*.probe")))

    def test_headroom_combines_ram_vram_scratch_and_probe_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake_usage = SimpleNamespace(total=500 * 1024 ** 3, used=100 * 1024 ** 3, free=400 * 1024 ** 3)
            with (
                patch("cinepulse.pipeline_runtime.shutil.disk_usage", return_value=fake_usage),
                patch("cinepulse.pipeline_runtime.ram_available_gb", return_value=41.5),
                patch("cinepulse.pipeline_runtime.vram_free_mb", return_value=7012.0),
                patch("cinepulse.pipeline_runtime.measure_scratch_write_mbps", return_value=(1280.0, 32 * 1024 ** 2)),
            ):
                headroom = measure_resource_headroom(root, gpu_index=0, probe_write=True)
            self.assertEqual(headroom.ram_available_gb, 41.5)
            self.assertEqual(headroom.vram_free_mb, 7012.0)
            self.assertAlmostEqual(headroom.scratch_free_gb, 400.0)
            self.assertEqual(headroom.scratch_write_mbps, 1280.0)
            self.assertEqual(headroom.probe_bytes, 32 * 1024 ** 2)

    def test_background_command_keeps_output_tail_and_reports_success(self) -> None:
        task = BackgroundCommand(
            [sys.executable, "-c", "print('H4_BACKGROUND_OK')"],
            poll_seconds=0.02,
        ).start()
        result = task.wait(timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.cancelled)
        self.assertIn("H4_BACKGROUND_OK", result.output_tail)
        self.assertTrue(task.done)

    def test_background_command_surfaces_child_failure_tail(self) -> None:
        task = BackgroundCommand(
            [sys.executable, "-c", "import sys; print('H4_FAIL_MARKER'); sys.exit(7)"],
            poll_seconds=0.02,
        ).start()
        with self.assertRaisesRegex(RuntimeError, "H4_FAIL_MARKER"):
            task.wait(timeout=10)
        self.assertTrue(task.done)

    def test_background_command_cancel_terminates_independent_process_group(self) -> None:
        task = BackgroundCommand(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            poll_seconds=0.02,
        ).start()
        deadline = time.monotonic() + 5.0
        while not task.running and time.monotonic() < deadline:
            time.sleep(0.01)
        task.cancel()
        result = task.wait(timeout=10)
        self.assertTrue(result.cancelled)
        self.assertTrue(task.done)


if __name__ == "__main__":
    unittest.main()
