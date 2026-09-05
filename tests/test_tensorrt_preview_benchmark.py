from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from scripts.tensorrt_preview_benchmark import TEMPORAL_DELTA_MAE_FLOOR, temporal_parity


class TensorRtPreviewBenchmarkTests(unittest.TestCase):
    def test_identical_motion_deltas_pass(self) -> None:
        baseline = [object(), object(), object()]
        candidate = [object(), object(), object()]
        values = {
            id(baseline[0]): np.zeros((36, 64), dtype=np.float32),
            id(baseline[1]): np.ones((36, 64), dtype=np.float32) * 10,
            id(baseline[2]): np.ones((36, 64), dtype=np.float32) * 20,
            id(candidate[0]): np.ones((36, 64), dtype=np.float32) * 5,
            id(candidate[1]): np.ones((36, 64), dtype=np.float32) * 15,
            id(candidate[2]): np.ones((36, 64), dtype=np.float32) * 25,
        }
        with patch("scripts.tensorrt_preview_benchmark._gray_frame", side_effect=lambda _ff, item: values[id(item)]):
            ok, mae = temporal_parity("ffmpeg", baseline, candidate)
        self.assertTrue(ok)
        self.assertEqual(0.0, mae)

    def test_duplicate_or_jittered_candidate_motion_fails(self) -> None:
        baseline = [object(), object(), object()]
        candidate = [object(), object(), object()]
        values = {
            id(baseline[0]): np.zeros((36, 64), dtype=np.float32),
            id(baseline[1]): np.ones((36, 64), dtype=np.float32) * 10,
            id(baseline[2]): np.ones((36, 64), dtype=np.float32) * 20,
            id(candidate[0]): np.zeros((36, 64), dtype=np.float32),
            id(candidate[1]): np.zeros((36, 64), dtype=np.float32),
            id(candidate[2]): np.ones((36, 64), dtype=np.float32) * 20,
        }
        with patch("scripts.tensorrt_preview_benchmark._gray_frame", side_effect=lambda _ff, item: values[id(item)]):
            ok, mae = temporal_parity("ffmpeg", baseline, candidate)
        self.assertFalse(ok)
        self.assertIsNotNone(mae)
        self.assertGreater(mae, TEMPORAL_DELTA_MAE_FLOOR)

    def test_frame_count_mismatch_is_rejected_before_sampling(self) -> None:
        ok, mae = temporal_parity("ffmpeg", [object(), object()], [object()])
        self.assertFalse(ok)
        self.assertIsNone(mae)


if __name__ == "__main__":
    unittest.main()
