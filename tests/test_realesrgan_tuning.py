from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cinepulse.realesrgan_tuning import (
    RealEsrganPolicy,
    RealEsrganSample,
    RealEsrganTuningKey,
    RealEsrganTuningStore,
    choose_proven_policy,
    downshift_policy,
    safe_candidates,
)


class RealEsrganTuningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = RealEsrganTuningStore(Path(self.temp.name) / "realesrgan-tuning.json")
        self.key = RealEsrganTuningKey("RTX Test", 8192, "999.1", "realesr-animevideov3", 1920, 1080, 2)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_legacy_fallback_is_always_first_candidate(self) -> None:
        candidates = safe_candidates(vram_mb=8192, cpu_threads=20, gpu_index=1, width=1920, height=1080)
        self.assertEqual(candidates[0], RealEsrganPolicy(256, 2, 2, 2, 1))

    def test_high_resolution_does_not_offer_512_tile(self) -> None:
        candidates = safe_candidates(vram_mb=24576, cpu_threads=28, width=7680, height=4320)
        self.assertFalse(any(item.tile == 512 for item in candidates))

    def test_command_args_select_gpu_explicitly(self) -> None:
        policy = RealEsrganPolicy(320, 3, 2, 3, 2)
        self.assertEqual(policy.command_args(), ["-t", "320", "-j", "3:2:3", "-g", "2"])

    def test_oom_and_integrity_failure_never_win(self) -> None:
        fallback = RealEsrganPolicy()
        fast_oom = RealEsrganSample(RealEsrganPolicy(512, 4, 2, 4), 4.0, False, oom=True, output_frames=20, expected_frames=20)
        corrupt = RealEsrganSample(RealEsrganPolicy(384, 3, 2, 3), 5.0, False, output_frames=19, expected_frames=20)
        good = RealEsrganSample(RealEsrganPolicy(320, 3, 2, 3), 8.0, True, output_frames=20, expected_frames=20)
        self.assertEqual(choose_proven_policy((fast_oom, corrupt, good), fallback=fallback), good.policy)

    def test_frame_count_mismatch_rejected_even_if_integrity_flag_true(self) -> None:
        sample = RealEsrganSample(RealEsrganPolicy(320, 3, 2, 3), 6.0, True, output_frames=9, expected_frames=10)
        self.assertFalse(sample.accepted)

    def test_downshift_reduces_pressure_after_oom(self) -> None:
        failed = RealEsrganPolicy(384, 3, 2, 3)
        candidates = (
            RealEsrganPolicy(256, 2, 2, 2),
            RealEsrganPolicy(320, 3, 2, 3),
            failed,
        )
        self.assertEqual(downshift_policy(failed, candidates), RealEsrganPolicy(256, 2, 2, 2))

    def test_store_only_records_accepted_policy(self) -> None:
        winner = RealEsrganPolicy(320, 3, 2, 3)
        recorded = self.store.record_samples(
            self.key,
            (
                RealEsrganSample(RealEsrganPolicy(384, 4, 2, 4), 4.0, False, oom=True, output_frames=10, expected_frames=10),
                RealEsrganSample(winner, 7.0, True, output_frames=10, expected_frames=10),
                RealEsrganSample(RealEsrganPolicy(), 9.0, True, output_frames=10, expected_frames=10),
            ),
        )
        self.assertEqual(recorded, winner)
        self.assertEqual(self.store.lookup(self.key), winner)

    def test_driver_change_invalidates_cache_key(self) -> None:
        policy = RealEsrganPolicy(320, 3, 2, 3)
        self.store.record_samples(
            self.key,
            (RealEsrganSample(policy, 7.0, True, output_frames=10, expected_frames=10),),
        )
        changed = RealEsrganTuningKey("RTX Test", 8192, "1000.0", "realesr-animevideov3", 1920, 1080, 2)
        self.assertIsNone(self.store.lookup(changed))

    def test_invalidate_removes_failed_cached_policy_and_records_reason(self) -> None:
        policy = RealEsrganPolicy(320, 3, 2, 3)
        other_key = RealEsrganTuningKey("RTX Test", 8192, "999.1", "realesr-animevideov3", 1280, 720, 2)
        other_policy = RealEsrganPolicy(256, 2, 2, 2)
        self.store.record_samples(
            self.key,
            (RealEsrganSample(policy, 7.0, True, output_frames=10, expected_frames=10),),
        )
        self.store.record_samples(
            other_key,
            (RealEsrganSample(other_policy, 5.0, True, output_frames=10, expected_frames=10),),
        )
        self.assertTrue(self.store.invalidate(self.key, reason="simulated runtime OOM"))
        self.assertIsNone(self.store.lookup(self.key))
        self.assertEqual(self.store.lookup(other_key), other_policy)
        payload = json.loads(self.store.path.read_text(encoding="utf-8"))
        tombstone = payload["invalidated"][self.key.token()]
        self.assertIn("runtime OOM", tombstone["reason"])
        self.assertFalse(self.store.invalidate(self.key, reason="second failure"))

    def test_corrupt_store_fails_closed(self) -> None:
        self.store.path.write_text("not-json", encoding="utf-8")
        self.assertIsNone(self.store.lookup(self.key))


if __name__ == "__main__":
    unittest.main()
