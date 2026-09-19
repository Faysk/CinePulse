from __future__ import annotations

import threading
import time
import unittest

import numpy as np

from cinepulse.vfx import (
    RenderCancelled,
    _parallel_vfx_frames,
    choose_vfx_frame_workers,
)


class FakeGenerator:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def make(self, frame_number, _bands, _loudness, _attack) -> bytes:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            # Make completion order intentionally differ from submission order.
            time.sleep(0.035 if frame_number == 0 else 0.01)
            return f"frame-{frame_number}".encode("ascii")
        finally:
            with self.lock:
                self.active -= 1


class VfxThroughputTests(unittest.TestCase):
    def test_worker_budget_scales_with_canvas_and_cpu_without_unbounded_4k_fanout(self) -> None:
        self.assertEqual(1, choose_vfx_frame_workers(3840, 2160, 3))
        self.assertEqual(3, choose_vfx_frame_workers(3840, 2160, 28))
        self.assertEqual(4, choose_vfx_frame_workers(2560, 1440, 28))
        self.assertEqual(6, choose_vfx_frame_workers(1920, 1080, 28))

    def test_parallel_generator_preserves_exact_frame_order(self) -> None:
        generator = FakeGenerator()
        energy = np.zeros((6, 3), dtype=np.float32)
        rms = np.zeros(6, dtype=np.float32)
        onset = np.zeros(6, dtype=np.float32)

        frames = list(
            _parallel_vfx_frames(
                generator,
                energy,
                rms,
                onset,
                workers=3,
                cancelled=lambda: False,
            )
        )

        self.assertEqual(list(range(6)), [index for index, _frame in frames])
        self.assertEqual(
            [f"frame-{index}".encode("ascii") for index in range(6)],
            [frame for _index, frame in frames],
        )
        self.assertGreaterEqual(generator.max_active, 2)

    def test_single_worker_path_remains_deterministic(self) -> None:
        generator = FakeGenerator()
        energy = np.zeros((3, 3), dtype=np.float32)
        rms = np.zeros(3, dtype=np.float32)
        onset = np.zeros(3, dtype=np.float32)
        frames = list(
            _parallel_vfx_frames(
                generator,
                energy,
                rms,
                onset,
                workers=1,
                cancelled=lambda: False,
            )
        )
        self.assertEqual([0, 1, 2], [index for index, _frame in frames])
        self.assertEqual(1, generator.max_active)

    def test_cancel_fails_fast_without_reordering_contract(self) -> None:
        generator = FakeGenerator()
        energy = np.zeros((4, 3), dtype=np.float32)
        rms = np.zeros(4, dtype=np.float32)
        onset = np.zeros(4, dtype=np.float32)
        calls = {"count": 0}

        def cancelled() -> bool:
            calls["count"] += 1
            return calls["count"] > 1

        with self.assertRaises(RenderCancelled):
            list(
                _parallel_vfx_frames(
                    generator,
                    energy,
                    rms,
                    onset,
                    workers=2,
                    cancelled=cancelled,
                )
            )


if __name__ == "__main__":
    unittest.main()
