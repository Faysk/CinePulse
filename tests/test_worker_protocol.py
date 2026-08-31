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


if __name__ == "__main__":
    unittest.main()
