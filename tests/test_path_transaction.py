from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cinepulse.path_transaction import path_mutation_transaction


ROOT = Path(__file__).resolve().parents[1]


class PathTransactionTests(unittest.TestCase):
    def test_transaction_is_reentrant_for_same_thread(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "state.json"
            with path_mutation_transaction(target, timeout=2.0):
                with path_mutation_transaction(target, timeout=2.0):
                    target.write_text("ok", encoding="utf-8")
            self.assertEqual("ok", target.read_text(encoding="utf-8"))

    def test_transaction_serializes_real_processes_without_lost_updates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "counter.txt"
            target.write_text("0", encoding="ascii")
            worker = r"""
import pathlib
import sys
import time
from cinepulse.path_transaction import path_mutation_transaction

path = pathlib.Path(sys.argv[1])
count = int(sys.argv[2])
for _ in range(count):
    with path_mutation_transaction(path, timeout=15.0):
        value = int(path.read_text(encoding="ascii"))
        time.sleep(0.01)
        path.write_text(str(value + 1), encoding="ascii")
"""
            env = os.environ.copy()
            env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
            workers = [
                subprocess.Popen(
                    [sys.executable, "-c", worker, str(target), "12"],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(4)
            ]
            failures: list[str] = []
            for process in workers:
                stdout, stderr = process.communicate(timeout=30)
                if process.returncode:
                    failures.append(f"code={process.returncode} stdout={stdout!r} stderr={stderr!r}")
            self.assertEqual([], failures)
            self.assertEqual(48, int(target.read_text(encoding="ascii")))


if __name__ == "__main__":
    unittest.main()
