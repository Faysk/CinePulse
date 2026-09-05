from __future__ import annotations

import inspect
import tempfile
import threading
import time
import unittest
from pathlib import Path

from cinepulse.job_lease import JobLease, LeaseBusy, LeaseOwnershipLost, _windows_process_api


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class JobLeaseTests(unittest.TestCase):
    def test_second_owner_is_rejected_while_heartbeat_is_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lease.json"
            clock = Clock()
            first = JobLease(
                path,
                "job-1",
                stale_after=10,
                clock=clock,
                pid=100,
                process_token=lambda pid: "start-100" if pid == 100 else "start-200",
                alive=lambda _pid: True,
            )
            first.acquire()
            second = JobLease(
                path,
                "job-1",
                stale_after=10,
                clock=clock,
                pid=200,
                process_token=lambda pid: "start-100" if pid == 100 else "start-200",
                alive=lambda _pid: True,
            )
            with self.assertRaises(LeaseBusy):
                second.acquire()

    def test_stale_heartbeat_does_not_steal_from_same_live_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lease.json"
            clock = Clock()
            owner = JobLease(
                path, "job-1", stale_after=10, clock=clock, pid=100,
                process_token=lambda _pid: "same-start", alive=lambda _pid: True,
            )
            owner.acquire()
            clock.value += 100
            challenger = JobLease(
                path, "job-1", stale_after=10, clock=clock, pid=200,
                process_token=lambda pid: "same-start" if pid == 100 else "challenger",
                alive=lambda _pid: True,
            )
            with self.assertRaises(LeaseBusy):
                challenger.acquire()

    def test_pid_reuse_allows_stale_takeover_after_start_token_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "lease.json"
            clock = Clock()
            original_token = {100: "old-start"}
            owner = JobLease(
                path, "job-1", stale_after=10, clock=clock, pid=100,
                process_token=lambda pid: original_token.get(pid), alive=lambda _pid: True,
            )
            owner.acquire()
            clock.value += 100
            original_token[100] = "recycled-start"
            challenger = JobLease(
                path, "job-1", stale_after=10, clock=clock, pid=200,
                process_token=lambda pid: original_token.get(pid, "new-owner"), alive=lambda _pid: True,
            )
            record = challenger.acquire()
            self.assertEqual(200, record.pid)
            self.assertTrue(list(root.glob("lease.json.stale-*")))

    def test_registered_live_subprocess_blocks_stale_takeover(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lease.json"
            clock = Clock()
            alive_pids = {100, 777}
            owner = JobLease(
                path, "job-1", stale_after=10, clock=clock, pid=100,
                process_token=lambda pid: "owner" if pid == 100 else None,
                alive=lambda pid: pid in alive_pids,
            )
            owner.acquire()
            owner.heartbeat(subprocesses=(777,))
            clock.value += 100
            alive_pids.remove(100)
            challenger = JobLease(
                path, "job-1", stale_after=10, clock=clock, pid=200,
                process_token=lambda _pid: None,
                alive=lambda pid: pid in alive_pids,
            )
            with self.assertRaises(LeaseBusy):
                challenger.acquire()

    def test_heartbeat_is_monotonic_by_progress_counter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lease = JobLease(Path(temporary) / "lease.json", "job-1")
            lease.acquire()
            first = lease.heartbeat(phase="rife", unit="segment-1", progress=True)
            second = lease.heartbeat(phase="rife", unit="segment-2", progress=True)
            self.assertEqual(first.progress_counter + 1, second.progress_counter)
            lease.release()

    def test_mutation_guard_serializes_competing_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lease.json"
            owner = JobLease(
                path, "job-1", pid=100, mutation_timeout=1.0,
                process_token=lambda pid: f"start-{pid}", alive=lambda _pid: True,
            )
            challenger = JobLease(
                path, "job-1", pid=200, mutation_timeout=1.0,
                process_token=lambda pid: f"start-{pid}", alive=lambda _pid: True,
            )
            entered = threading.Event()
            finished = threading.Event()
            errors: list[BaseException] = []

            def contender() -> None:
                entered.set()
                try:
                    with challenger._mutation_guard():
                        pass
                except BaseException as exc:  # pragma: no cover - diagnostic path
                    errors.append(exc)
                finally:
                    finished.set()

            with owner._mutation_guard():
                thread = threading.Thread(target=contender)
                thread.start()
                self.assertTrue(entered.wait(0.5))
                time.sleep(0.05)
                self.assertFalse(finished.is_set(), "challenger entered while owner still held mutation guard")
            self.assertTrue(finished.wait(1.0))
            thread.join(timeout=1.0)
            self.assertFalse(errors)

    def test_heartbeat_refuses_foreign_nonce(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "lease.json"
            lease = JobLease(path, "job-1")
            lease.acquire()
            payload = __import__("json").loads(path.read_text(encoding="utf-8"))
            payload["nonce"] = "foreign-owner"
            path.write_text(__import__("json").dumps(payload), encoding="utf-8")
            with self.assertRaises(LeaseOwnershipLost):
                lease.heartbeat(progress=True)

    def test_windows_api_declares_pointer_sized_handle_contract(self) -> None:
        source = inspect.getsource(_windows_process_api)
        self.assertIn("wintypes.HANDLE", source)
        self.assertIn("OpenProcess.restype", source)
        self.assertIn("CloseHandle.argtypes", source)


if __name__ == "__main__":
    unittest.main()
