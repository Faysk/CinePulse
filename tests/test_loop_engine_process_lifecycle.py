from __future__ import annotations

import queue
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cinepulse.loop_engine import LoopMusicApp


class _CloseableLines(list):
    def __init__(self, lines=()) -> None:
        super().__init__(lines)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, lines=(), *, poll_value=0, returncode=0) -> None:
        self.stdout = _CloseableLines(lines)
        self._poll_value = poll_value
        self._returncode = returncode

    def poll(self):
        return self._poll_value

    def wait(self):
        return self._returncode


def _app() -> LoopMusicApp:
    app = LoopMusicApp.__new__(LoopMusicApp)
    app._events = queue.Queue()
    app._cancelled = False
    app._process = None
    return app


class ClassicProcessLifecycleTests(unittest.TestCase):
    def test_ffmpeg_progress_pipe_is_closed_and_process_is_grouped(self) -> None:
        app = _app()
        process = _FakeProcess(["out_time=00:00:00.500000\n"])
        captured = {}

        def factory(_command, **kwargs):
            captured.update(kwargs)
            return process

        with (
            patch("cinepulse.loop_engine.subprocess.Popen", side_effect=factory),
            patch("cinepulse.loop_engine.popen_group_kwargs", return_value={"start_new_session": True}),
        ):
            app._run_ffmpeg(["ffmpeg"], 1.0, 0.0, 1.0)

        self.assertTrue(process.stdout.closed)
        self.assertTrue(captured["start_new_session"])

    def test_ai_output_pipe_is_closed_and_process_is_grouped(self) -> None:
        app = _app()
        process = _FakeProcess(["frame 1\n"])
        captured = {}

        def factory(_command, **kwargs):
            captured.update(kwargs)
            return process

        with tempfile.TemporaryDirectory() as temporary, (
            patch("cinepulse.loop_engine.subprocess.Popen", side_effect=factory),
            patch("cinepulse.loop_engine.popen_group_kwargs", return_value={"start_new_session": True}),
        ):
            app._run_ai_process(["realesrgan"], Path(temporary), 1, 0.0, 1.0)

        self.assertTrue(process.stdout.closed)
        self.assertTrue(captured["start_new_session"])

    def test_classic_cancel_terminates_entire_process_tree(self) -> None:
        app = _app()
        app._busy = True
        app.status = SimpleNamespace(set=lambda _value: None)
        process = _FakeProcess(poll_value=None)
        app._process = process

        with patch("cinepulse.loop_engine.terminate_process_tree") as terminate:
            app._cancel()

        self.assertTrue(app._cancelled)
        terminate.assert_called_once_with(process, grace_seconds=2.0)


if __name__ == "__main__":
    unittest.main()
