from __future__ import annotations

import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.studio import VideoOptimizerStudio, _finalize_piped_process


class _CloseableLines(list):
    def __init__(self, lines=()) -> None:
        super().__init__(lines)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, lines=(), *, running: bool = False, returncode: int = 0) -> None:
        self.stdout = _CloseableLines(lines)
        self._running = running
        self.returncode = returncode
        self.pid = 4242

    def poll(self):
        return None if self._running else self.returncode

    def wait(self, timeout=None):
        del timeout
        self._running = False
        return self.returncode


class _FakeThread:
    def __init__(self) -> None:
        self.joins = 0

    def join(self, timeout=None) -> None:
        del timeout
        self.joins += 1


def _studio() -> VideoOptimizerStudio:
    app = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
    app._cancelled = False
    app._events = queue.Queue()
    app._process = None
    app._log = lambda _message: None
    app._push_progress = lambda _value: None
    return app


class StudioNeuralProcessLifecycleTests(unittest.TestCase):
    def test_shared_finalizer_kills_live_child_and_closes_stdout(self) -> None:
        process = _FakeProcess(running=True)
        reader = _FakeThread()

        def terminate(target, _log=None, *, grace_seconds=0):
            self.assertIs(target, process)
            self.assertEqual(2.0, grace_seconds)
            process._running = False

        with patch("cinepulse.studio.terminate_process_tree", side_effect=terminate) as kill:
            _finalize_piped_process(process, reader, lambda _message: None)

        kill.assert_called_once()
        self.assertTrue(process.stdout.closed)
        self.assertGreaterEqual(reader.joins, 1)

    def test_realesrgan_success_closes_output_pipe(self) -> None:
        app = _studio()
        process = _FakeProcess(["done\n"], returncode=0)
        with tempfile.TemporaryDirectory() as temporary, patch(
            "cinepulse.studio.subprocess.Popen", return_value=process
        ):
            app._run_ai(["realesrgan"], Path(temporary), 1, 0.0, 1.0)

        self.assertTrue(process.stdout.closed)

    def test_realesrgan_progress_exception_reaps_child_and_closes_pipe(self) -> None:
        app = _studio()
        process = _FakeProcess(["working\n"], running=True)
        app._push_progress = lambda _value: (_ for _ in ()).throw(RuntimeError("progress exploded"))

        def terminate(target, _log=None, *, grace_seconds=0):
            del _log, grace_seconds
            target._running = False

        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch("cinepulse.studio.subprocess.Popen", return_value=process),
                patch("cinepulse.studio.terminate_process_tree", side_effect=terminate) as kill,
                patch("cinepulse.studio.time.sleep", return_value=None),
            ):
                with self.assertRaisesRegex(RuntimeError, "progress exploded"):
                    app._run_ai(["realesrgan"], Path(temporary), 1, 0.0, 1.0)

        self.assertGreaterEqual(kill.call_count, 1)
        self.assertTrue(process.stdout.closed)


if __name__ == "__main__":
    unittest.main()
