from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.rife_tuning import (
    RifePolicy,
    RifeSample,
    RifeTuningKey,
    RifeTuningStore,
    downshift_policy,
    fallback_policy,
    safe_candidates,
)


class RifeTuningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = RifeTuningStore(Path(self.temp.name) / "rife-tuning.json")
        self.key = RifeTuningKey("RTX Test", 8192, "999.1", "rife-v4.6", 3840, 2160)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_uhd_fallback_preserves_conservative_jobs(self) -> None:
        self.assertEqual(fallback_policy(uhd=True), RifePolicy("1:1:1", 0))

    def test_uhd_candidates_keep_fallback_first(self) -> None:
        values = safe_candidates(uhd=True, vram_mb=8192, gpu_index=1)
        self.assertEqual(values[0], RifePolicy("1:1:1", 1))
        self.assertIn(RifePolicy("1:2:1", 1), values)

    def test_low_vram_uhd_does_not_offer_more_aggressive_jobs(self) -> None:
        values = safe_candidates(uhd=True, vram_mb=4096)
        self.assertEqual(values, (RifePolicy("1:1:1", 0),))

    def test_bad_frame_count_black_frame_or_oom_never_accept(self) -> None:
        policy = RifePolicy("1:2:1")
        self.assertFalse(RifeSample(policy, 5.0, True, output_frames=9, expected_frames=10).accepted)
        self.assertFalse(RifeSample(policy, 5.0, True, output_frames=10, expected_frames=10, black_frame_ok=False).accepted)
        self.assertFalse(RifeSample(policy, 5.0, False, oom=True, output_frames=10, expected_frames=10).accepted)

    def test_store_requires_baseline_first_and_passing(self) -> None:
        fallback = RifePolicy("1:1:1")
        fast = RifePolicy("1:2:1")
        rejected = self.store.record_samples(
            self.key,
            (
                RifeSample(fallback, 10.0, False, output_frames=20, expected_frames=20),
                RifeSample(fast, 5.0, True, output_frames=20, expected_frames=20),
            ),
            fallback=fallback,
        )
        self.assertIsNone(rejected)
        self.assertIsNone(self.store.lookup(self.key))

    def test_store_records_fastest_integrity_approved_policy(self) -> None:
        fallback = RifePolicy("1:1:1")
        fast = RifePolicy("1:2:1")
        winner = self.store.record_samples(
            self.key,
            (
                RifeSample(fallback, 10.0, True, output_frames=20, expected_frames=20),
                RifeSample(fast, 6.0, True, output_frames=20, expected_frames=20),
            ),
            fallback=fallback,
        )
        self.assertEqual(winner, fast)
        self.assertEqual(self.store.lookup(self.key), fast)

    def test_driver_change_invalidates_key(self) -> None:
        fallback = RifePolicy("1:1:1")
        self.store.record_samples(
            self.key,
            (RifeSample(fallback, 10.0, True, output_frames=20, expected_frames=20),),
            fallback=fallback,
        )
        changed = RifeTuningKey("RTX Test", 8192, "1000.0", "rife-v4.6", 3840, 2160)
        self.assertIsNone(self.store.lookup(changed))

    def test_downshift_returns_lower_pressure_or_fallback(self) -> None:
        fallback = RifePolicy("1:1:1")
        failed = RifePolicy("2:2:2")
        values = (fallback, RifePolicy("1:2:1"), failed)
        self.assertEqual(downshift_policy(failed, values, fallback=fallback), fallback)

    def test_corrupt_store_fails_closed(self) -> None:
        self.store.path.write_text("not-json", encoding="utf-8")
        self.assertIsNone(self.store.lookup(self.key))


if __name__ == "__main__":
    unittest.main()
