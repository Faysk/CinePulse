from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from cinepulse.job_store import JobStore
from cinepulse.recovery_bootstrap import run_recovery_bootstrap
from cinepulse.recovery_rollout import write_ring
from cinepulse.render_job import RenderJobManifest


class RecoveryBootstrapTests(unittest.TestCase):
    def _paused_job(self, logs: Path) -> None:
        job_dir = logs / "renders" / "job-1"
        job_dir.mkdir(parents=True)
        manifest = RenderJobManifest.new("job-1", source={"path_hint": ""}, now=1.0)
        for state in ("preflight", "running", "pause_requested", "paused"):
            manifest = manifest.transition(state, now=manifest.updated_at + 1)
        JobStore(job_dir / "manifest.json").create(manifest)

    def test_ring1_does_not_run_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            logs = data / "logs"
            config = data / "config"
            config.mkdir()
            write_ring(config / "recovery-flags.json", 1)
            self._paused_job(logs)
            result = run_recovery_bootstrap(data, logs, config)
            self.assertEqual("disabled", result.mode)
            self.assertEqual(0, result.discovered)
            self.assertFalse((data / "recovery-discovery.json").exists())

    def test_ring3_runs_read_only_discovery_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            logs = data / "logs"
            config = data / "config"
            config.mkdir()
            write_ring(config / "recovery-flags.json", 3)
            self._paused_job(logs)
            before = JobStore(logs / "renders" / "job-1" / "manifest.json").load()
            result = run_recovery_bootstrap(data, logs, config)
            after = JobStore(logs / "renders" / "job-1" / "manifest.json").load()
            self.assertEqual("dry-run", result.mode)
            self.assertEqual(1, result.discovered)
            self.assertTrue(Path(result.snapshot).is_file())
            self.assertEqual(before, after)


    def test_ring3_backup_only_discovery_does_not_restore_primary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary)
            logs = data / "logs"
            config = data / "config"
            config.mkdir()
            write_ring(config / "recovery-flags.json", 3)
            self._paused_job(logs)
            job_dir = logs / "renders" / "job-1"
            primary = job_dir / "manifest.json"
            backup = job_dir / "manifest.json.bak"
            shutil.copy2(primary, backup)
            backup_before = backup.read_bytes()
            primary.unlink()

            result = run_recovery_bootstrap(data, logs, config)

            self.assertEqual("dry-run", result.mode)
            self.assertEqual(1, result.discovered)
            self.assertFalse(primary.exists())
            self.assertEqual(backup_before, backup.read_bytes())
            self.assertEqual([], list(job_dir.glob("manifest.json.corrupt-*")))



if __name__ == "__main__":
    unittest.main()
