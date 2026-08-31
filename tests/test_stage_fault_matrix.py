from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.stage_adapter import AtomicStageAdapter, file_validator
from cinepulse.stage_checkpoint import StageCheckpointStore


class InjectedFault(RuntimeError):
    pass


class StageFaultMatrixTests(unittest.TestCase):
    def test_fault_points_converge_to_same_committed_result(self) -> None:
        for fault_point in (
            "before_produce",
            "after_produce",
            "after_validate",
            "after_promote",
            "after_checkpoint",
        ):
            with self.subTest(fault_point=fault_point), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                checkpoint = StageCheckpointStore(
                    root / "checkpoint.json",
                    job_id="job-1",
                    attempt_id="attempt-1",
                    stage="rife",
                    policy_fingerprint="policy-v1",
                )
                final = root / "segment.mkv"
                produced = {"count": 0}
                injected = {"done": False}

                def producer(partial: Path) -> None:
                    produced["count"] += 1
                    partial.write_bytes(b"canonical-result")

                def fault(point: str, _unit: str) -> None:
                    if point == fault_point and not injected["done"]:
                        injected["done"] = True
                        raise InjectedFault(point)

                adapter = AtomicStageAdapter(checkpoint, fault_hook=fault)
                with self.assertRaises(InjectedFault):
                    adapter.execute_unit(
                        unit_id="unit-1",
                        ordinal=1,
                        final=final,
                        producer=producer,
                        validator=file_validator(expected_bytes=b"canonical-result"),
                    )

                resumed = AtomicStageAdapter(checkpoint)
                resumed.execute_unit(
                    unit_id="unit-1",
                    ordinal=1,
                    final=final,
                    producer=producer,
                    validator=file_validator(expected_bytes=b"canonical-result"),
                )
                self.assertEqual(b"canonical-result", final.read_bytes())
                self.assertEqual("committed", checkpoint.committed("unit-1")["state"])
                # Once promotion happened, resume must reconcile rather than
                # running the expensive producer a second time.
                if fault_point in {"after_promote", "after_checkpoint"}:
                    self.assertEqual(1, produced["count"])
                else:
                    self.assertGreaterEqual(produced["count"], 1)


if __name__ == "__main__":
    unittest.main()
