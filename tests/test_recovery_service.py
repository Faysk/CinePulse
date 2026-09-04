from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.job_lease import JobLease
from cinepulse.job_store import JobStore
from cinepulse.recovery_service import RecoveryService
from cinepulse.render_job import RenderJobManifest
from cinepulse.ui.recovery_lab import card_model


class RecoveryServiceTests(unittest.TestCase):
    def _job(self, root: Path, job_id: str, state: str, *, source: Path | None = None, committed: int = 0, total: int | None = None) -> Path:
        job_dir = root / job_id
        job_dir.mkdir(parents=True)
        manifest = RenderJobManifest.new(job_id, source={"path_hint": str(source) if source else ""}, now=1.0)
        route = {
            "preflight": ["preflight"],
            "running": ["preflight", "running"],
            "paused": ["preflight", "running", "pause_requested", "paused"],
            "recoverable": ["preflight", "running", "pause_requested", "paused", "recoverable"],
            "verifying": ["preflight", "running", "verifying"],
            "complete": ["preflight", "running", "verifying", "complete"],
            "blocked": ["preflight", "blocked"],
            "cancelled": ["preflight", "cancelled"],
        }[state]
        for target in route:
            manifest = manifest.transition(target, now=manifest.updated_at + 1)
        if committed or total is not None:
            manifest = manifest.with_phase_progress(
                name="rife", units_total=total, units_committed=committed,
                unit_kind="segments", last_commit=f"segment-{committed}" if committed else None,
                now=manifest.updated_at + 1,
            )
        JobStore(job_dir / "manifest.json").create(manifest)
        return job_dir

    def test_paused_job_is_discovered_as_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"media")
            self._job(root, "job-1", "paused", source=source, committed=25, total=100)
            candidates = RecoveryService(root).discover()
            self.assertEqual(1, len(candidates))
            candidate = candidates[0]
            self.assertEqual("recoverable", candidate.classification)
            self.assertIn("retomar", candidate.actions)
            self.assertEqual(25, candidate.units_committed)
            self.assertEqual(100, candidate.units_total)

    def test_live_lease_is_active_and_never_offers_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"media")
            job_dir = self._job(root, "job-1", "running", source=source)
            lease = JobLease(job_dir / "lease.json", "job-1")
            lease.acquire(phase="rife")
            try:
                candidate = RecoveryService(root).discover()[0]
                self.assertEqual("active", candidate.classification)
                self.assertNotIn("retomar", candidate.actions)
                self.assertTrue(candidate.owner_active)
            finally:
                lease.release()

    def test_missing_source_is_blocked_without_mutating_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "gone.mp4"
            job_dir = self._job(root, "job-1", "paused", source=missing)
            before = JobStore(job_dir / "manifest.json").load()
            candidate = RecoveryService(root).discover()[0]
            after = JobStore(job_dir / "manifest.json").load()
            self.assertEqual("blocked", candidate.classification)
            self.assertIn("reconectar_fonte", candidate.actions)
            self.assertEqual(before, after)

    def test_complete_job_is_not_reintroduced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._job(root, "job-1", "complete")
            self.assertEqual([], RecoveryService(root).discover())

    def test_card_separates_phase_progress_from_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.write_bytes(b"media")
            self._job(root, "job-1", "paused", source=source, committed=94, total=100)
            model = card_model(RecoveryService(root).discover()[0])
            self.assertIn("94.00% da fase", model.phase_progress)
            self.assertNotEqual("Arquivo aprovado", model.badge)
            self.assertEqual("Recuperado do disco", model.origin)


if __name__ == "__main__":
    unittest.main()
