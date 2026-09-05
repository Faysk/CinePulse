from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cinepulse.cpu_tuning import CpuTuningKey, CpuTuningSample, CpuTuningStore
from cinepulse.resource_scheduler import CpuTopology


class CpuTuningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "cpu-tuning.json"
        self.store = CpuTuningStore(self.path)
        self.topology = CpuTopology(logical_cpus=20, physical_cores=14, source="test")
        self.key = CpuTuningKey.from_topology("encode", self.topology, mode="dedicated", gpu_active=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_no_evidence_returns_none(self) -> None:
        self.assertIsNone(self.store.lookup(self.key, max_threads=18))

    def test_fast_integrity_failure_never_wins(self) -> None:
        chosen = self.store.record_samples(
            self.key,
            (
                CpuTuningSample(8, 20.0, True),
                CpuTuningSample(16, 8.0, False),
                CpuTuningSample(12, 13.0, True),
            ),
            fallback_threads=8,
        )
        self.assertEqual(chosen, 12)
        self.assertEqual(self.store.lookup(self.key, max_threads=18), 12)

    def test_all_failed_samples_are_not_persisted(self) -> None:
        chosen = self.store.record_samples(
            self.key,
            (CpuTuningSample(8, 10.0, False), CpuTuningSample(12, 8.0, False)),
            fallback_threads=8,
        )
        self.assertIsNone(chosen)
        self.assertFalse(self.path.exists())

    def test_saved_winner_never_overrides_smaller_user_cap(self) -> None:
        self.store.record_samples(
            self.key,
            (CpuTuningSample(12, 10.0, True), CpuTuningSample(16, 8.0, True)),
            fallback_threads=12,
        )
        self.assertEqual(self.store.lookup(self.key, max_threads=20), 16)
        self.assertIsNone(self.store.lookup(self.key, max_threads=10))

    def test_topology_or_stage_mismatch_does_not_reuse_policy(self) -> None:
        self.store.record_samples(
            self.key,
            (CpuTuningSample(12, 10.0, True),),
            fallback_threads=12,
        )
        other = CpuTuningKey.from_topology("scale", self.topology, mode="dedicated", gpu_active=True)
        self.assertIsNone(self.store.lookup(other, max_threads=20))

    def test_corrupt_cache_fails_closed(self) -> None:
        self.path.write_text("{ definitely not json", encoding="utf-8")
        self.assertIsNone(self.store.lookup(self.key, max_threads=20))

    def test_record_contains_auditable_samples(self) -> None:
        self.store.record_samples(
            self.key,
            (CpuTuningSample(8, 20.0, True), CpuTuningSample(12, 12.0, True)),
            fallback_threads=8,
        )
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        record = payload["records"][self.key.token()]
        self.assertTrue(record["integrity_ok"])
        self.assertEqual(record["threads"], 12)
        self.assertEqual(record["sample_count"], 2)
        self.assertEqual(record["verified_sample_count"], 2)


if __name__ == "__main__":
    unittest.main()
