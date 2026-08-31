from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cinepulse.job_store import JobStore
from cinepulse.recovery_migration import attach_manifest_reference, classify_legacy_job, migrate_legacy_job


class RecoveryMigrationTests(unittest.TestCase):
    def _legacy(self, root: Path, job_id: str = "job-1", *, with_contracts: bool = True, fingerprint: str = "abc") -> Path:
        job_dir = root / job_id
        job_dir.mkdir()
        (job_dir / "job.json").write_text(json.dumps({
            "schema": 1,
            "job_id": job_id,
            "status": "running",
            "started_at": 10.0,
            "settings": {"video": "source.mp4"},
        }), encoding="utf-8")
        (job_dir / "plan.json").write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
        if with_contracts:
            (job_dir / "contracts.json").write_text(json.dumps({
                "schema": 1,
                "job_id": job_id,
                "verification_expected": {"width": 3840, "height": 2160, "fps": 60},
            }), encoding="utf-8")
        return job_dir

    def test_high_confidence_dry_run_never_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job_dir = self._legacy(Path(temporary))
            classification = classify_legacy_job(job_dir)
            self.assertEqual("high", classification.confidence)
            result = migrate_legacy_job(job_dir, dry_run=True)
            self.assertFalse(result.migrated)
            self.assertFalse((job_dir / "manifest.json").exists())

    def test_high_confidence_migration_creates_interrupted_manifest_beside_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job_dir = self._legacy(Path(temporary))
            result = migrate_legacy_job(job_dir, dry_run=False)
            self.assertTrue(result.migrated)
            manifest = JobStore(job_dir / "manifest.json").load()
            self.assertEqual("interrupted", manifest.state)
            self.assertEqual("abc", manifest.render_plan["fingerprint"])
            self.assertEqual(3840, manifest.expectation["width"])
            self.assertTrue((job_dir / "job.json").is_file())
            self.assertTrue((job_dir / "plan.json").is_file())

    def test_medium_confidence_is_read_only_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job_dir = self._legacy(Path(temporary), with_contracts=False)
            self.assertEqual("medium", classify_legacy_job(job_dir).confidence)
            result = migrate_legacy_job(job_dir, dry_run=False)
            self.assertFalse(result.migrated)
            self.assertFalse((job_dir / "manifest.json").exists())

    def test_low_confidence_never_mutates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job_dir = Path(temporary) / "orphan"
            job_dir.mkdir()
            (job_dir / "segment_00001.mkv").write_bytes(b"orphan")
            classification = classify_legacy_job(job_dir)
            self.assertEqual("low", classification.confidence)
            self.assertFalse(migrate_legacy_job(job_dir, dry_run=False).migrated)

    def test_queue_reference_migration_preserves_unrelated_items(self) -> None:
        items = [
            {"id": 1, "job_id": "job-1", "status": "Interrompido"},
            {"id": 2, "job_id": "job-2", "status": "Aguardando"},
        ]
        migrated = attach_manifest_reference(items, job_id="job-1", manifest_reference="renders/job-1/manifest.json")
        self.assertEqual("renders/job-1/manifest.json", migrated[0]["manifest"])
        self.assertEqual("history", migrated[0]["recovery_origin"])
        self.assertNotIn("manifest", migrated[1])
        self.assertNotIn("manifest", items[0])


if __name__ == "__main__":
    unittest.main()
