from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cinepulse.job_store import JobStore, ManifestConflict, ManifestStoreError
from cinepulse.render_job import RenderJobManifest


class JobStoreTests(unittest.TestCase):
    def test_create_save_and_compare_and_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "manifest.json")
            created = store.create(RenderJobManifest.new("job-1", now=1.0))
            updated = created.transition("preflight", now=2.0)
            saved = store.save(updated, expected_revision=0)
            self.assertEqual(1, saved.revision)
            with self.assertRaises(ManifestConflict):
                store.save(saved.transition("running", now=3.0), expected_revision=0)
            self.assertEqual(1, store.load().revision)

    def test_backup_recovers_truncated_primary_without_losing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = JobStore(root / "manifest.json")
            first = store.create(RenderJobManifest.new("job-1", now=1.0))
            second = store.save(first.transition("preflight", now=2.0), expected_revision=0)
            third = store.save(second.transition("running", now=3.0), expected_revision=1)
            self.assertEqual(2, third.revision)
            store.path.write_text("{truncated", encoding="utf-8")
            recovered = store.load(recover_backup=True)
            self.assertEqual(1, recovered.revision)
            self.assertEqual("preflight", recovered.state)
            self.assertTrue(list(root.glob("manifest.json.corrupt-*")))
            persisted = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(1, persisted["revision"])

    def test_both_primary_and_backup_invalid_are_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "manifest.json")
            store.path.write_text("bad", encoding="utf-8")
            store.backup_path.write_text("also bad", encoding="utf-8")
            with self.assertRaises(ManifestStoreError):
                store.load(recover_backup=True)

    def test_initialize_enters_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "manifest.json")
            manifest = store.initialize("job-1", source={"path_hint": "source.mp4"})
            self.assertEqual("preflight", manifest.state)
            self.assertEqual(1, manifest.revision)

    def test_update_requires_mutator_to_return_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = JobStore(Path(temporary) / "manifest.json")
            store.create(RenderJobManifest.new("job-1", now=1.0))
            with self.assertRaises(TypeError):
                store.update(lambda _current: {})
            self.assertEqual(0, store.load().revision)


if __name__ == "__main__":
    unittest.main()
