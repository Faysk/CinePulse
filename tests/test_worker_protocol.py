from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.worker_protocol import WorkerCommand, WorkerCommandQueue, WorkerReply


class WorkerProtocolTests(unittest.TestCase):
    def test_command_survives_submit_claim_ack_and_reply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            queue = WorkerCommandQueue(Path(temporary), "job-1")
            command = WorkerCommand.create("job-1", "pause", {"reason": "user"})
            queue.submit(command)
            claimed = queue.next()
            self.assertIsNotNone(claimed)
            loaded, path = claimed
            self.assertEqual(command.request_id, loaded.request_id)
            reply = WorkerReply(
                request_id=command.request_id,
                job_id="job-1",
                ok=True,
                state="paused",
                message="ok",
                payload={"unit": 12},
                created_at=123.0,
            )
            queue.acknowledge(path, reply)
            restored = queue.read_reply(command.request_id)
            self.assertTrue(restored.ok)
            self.assertEqual("paused", restored.state)
            self.assertFalse(list(queue.processing.glob("*.json")))
            self.assertTrue(list(queue.done.glob("*.json")))

    def test_commands_are_claimed_in_submission_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            queue = WorkerCommandQueue(Path(temporary), "job-1")
            first = WorkerCommand.create("job-1", "status")
            second = WorkerCommand.create("job-1", "pause")
            queue.submit(first)
            queue.submit(second)
            loaded, _path = queue.next()
            self.assertEqual(first.request_id, loaded.request_id)

    def test_foreign_job_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            queue = WorkerCommandQueue(Path(temporary), "job-1")
            with self.assertRaisesRegex(RuntimeError, "job_id"):
                queue.submit(WorkerCommand.create("job-2", "status"))


    def test_claimed_command_is_requeued_after_worker_crash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = WorkerCommandQueue(root, "job-1")
            command = WorkerCommand.create("job-1", "cancel")
            queue.submit(command)
            claimed = queue.next()
            self.assertIsNotNone(claimed)
            loaded, claimed_path = claimed
            self.assertEqual(command.request_id, loaded.request_id)
            self.assertTrue(claimed_path.is_file())
            self.assertFalse(list(queue.inbox.glob("*.json")))

            restarted = WorkerCommandQueue(root, "job-1")
            recovered = restarted.recover_processing()
            self.assertEqual(1, recovered["requeued"])
            loaded_again, _path = restarted.next()
            self.assertEqual(command.request_id, loaded_again.request_id)

    def test_reply_written_before_crash_finalizes_without_reexecuting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = WorkerCommandQueue(root, "job-1")
            command = WorkerCommand.create("job-1", "pause")
            queue.submit(command)
            loaded, claimed_path = queue.next()
            reply = WorkerReply(
                request_id=loaded.request_id,
                job_id="job-1",
                ok=True,
                state="paused",
                message="ok",
                payload={},
                created_at=123.0,
            )
            # Simulate crash after the durable reply is written but before the
            # processing file is moved to done.
            queue._atomic(queue.replies / f"{reply.request_id}.json", reply.to_dict())
            self.assertTrue(claimed_path.is_file())

            restarted = WorkerCommandQueue(root, "job-1")
            recovered = restarted.recover_processing()
            self.assertEqual(1, recovered["finalized"])
            self.assertIsNone(restarted.next())
            self.assertTrue(restarted.read_reply(reply.request_id).ok)
            self.assertFalse(list(restarted.processing.glob("*.json")))

    def test_invalid_processing_command_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = WorkerCommandQueue(root, "job-1")
            broken = queue.processing / "broken.json"
            broken.write_text("{not-json", encoding="utf-8")
            recovered = queue.recover_processing()
            self.assertEqual(1, recovered["invalid"])
            self.assertFalse(broken.exists())
            self.assertTrue(list(queue.done.glob("broken.invalid-*.json")))


if __name__ == "__main__":
    unittest.main()
