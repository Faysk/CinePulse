from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.job_store import JobStore
from cinepulse.render_job import RenderJobManifest
from cinepulse.render_worker import RenderWorker
from cinepulse.worker_protocol import WorkerCommand


class RenderWorkerTests(unittest.TestCase):
    def _worker(self, root: Path) -> RenderWorker:
        store = JobStore(root / "manifest.json")
        store.create(RenderJobManifest.new("job-1", now=1.0))
        return RenderWorker(root, "job-1", stale_after=1.0)

    def test_worker_acquires_job_and_finishes_execution_in_verifying(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            worker = self._worker(Path(temporary))

            def executor(context):
                context.checkpoint(phase="rife", unit="segment-1")
                context.checkpoint(phase="rife", unit="segment-2")

            result = worker.run(executor)
            self.assertEqual("verifying", result.state)
            self.assertGreaterEqual(result.revision, 3)
            self.assertFalse((Path(temporary) / "lease.json").exists())
            self.assertTrue(list(Path(temporary).glob("lease.json.released-*")))

    def test_pause_command_stops_at_checkpoint_and_is_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worker = self._worker(root)
            worker.commands.submit(WorkerCommand.create("job-1", "pause"))

            def executor(context):
                context.checkpoint(phase="rife", unit="segment-1")
                self.fail("executor should stop on the safe boundary")

            paused = worker.run(executor)
            self.assertEqual("paused", paused.state)

            resumed_worker = RenderWorker(root, "job-1", stale_after=1.0)
            resumed = resumed_worker.run(lambda context: context.checkpoint(phase="rife", unit="segment-2"))
            self.assertEqual("verifying", resumed.state)

    def test_cancel_command_preserves_manifest_and_marks_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worker = self._worker(root)
            worker.commands.submit(WorkerCommand.create("job-1", "cancel"))
            result = worker.run(lambda context: context.checkpoint(phase="rife", unit="segment-1"))
            self.assertEqual("cancelled", result.state)
            self.assertTrue((root / "manifest.json").is_file())

    def test_cancel_after_pause_request_reaches_cancelled_through_valid_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worker = self._worker(root)
            worker.commands.submit(WorkerCommand.create("job-1", "pause"))
            worker.commands.submit(WorkerCommand.create("job-1", "cancel"))
            result = worker.run(lambda context: context.checkpoint(phase="rife", unit="segment-1"))
            self.assertEqual("cancelled", result.state)
            stored = JobStore(root / "manifest.json").load()
            self.assertEqual("cancelled", stored.state)
            self.assertEqual("worker_cancelled", stored.reason)

    def test_executor_failure_is_structured_and_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            worker = self._worker(root)
            with self.assertRaisesRegex(ValueError, "kaboom"):
                worker.run(lambda _context: (_ for _ in ()).throw(ValueError("kaboom")))
            manifest = JobStore(root / "manifest.json").load()
            self.assertEqual("blocked", manifest.state)
            self.assertEqual("WORKER-FAILED", manifest.last_error["code"])


if __name__ == "__main__":
    unittest.main()
