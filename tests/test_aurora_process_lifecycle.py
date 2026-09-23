from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from cinepulse import aurora


class _FakeStdin:
    def __init__(self) -> None:
        self.closed = False
        self.writes = 0

    def write(self, payload: bytes) -> int:
        self.writes += 1
        return len(payload)

    def close(self) -> None:
        self.closed = True


class _FakeStdout(list):
    def __init__(self, lines=()) -> None:
        super().__init__(lines)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeProcess:
    def __init__(self, *, returncode: int = 0, running: bool = False) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout()
        self.returncode = returncode
        self._running = running

    def poll(self):
        return None if self._running else self.returncode

    def wait(self):
        self._running = False
        return self.returncode


class AuroraProcessLifecycleTests(unittest.TestCase):
    @staticmethod
    def _analysis():
        return (
            np.asarray([[0.2, 0.3, 0.4]], dtype=np.float32),
            np.asarray([0.5], dtype=np.float32),
            np.asarray([0.1], dtype=np.float32),
        )

    def test_success_closes_pipes_and_uses_process_group(self) -> None:
        process = _FakeProcess(returncode=0)
        captured = {}
        changed = []
        progress = []

        def factory(_command, **kwargs):
            captured.update(kwargs)
            return process

        with (
            patch("cinepulse.aurora._decode_audio", return_value=np.zeros(16, dtype=np.float32)),
            patch("cinepulse.aurora._analyze_audio", return_value=self._analysis()),
            patch(
                "cinepulse.aurora.AuroraFrameGenerator",
                return_value=type("Generator", (), {"make": lambda self, *_args: b"frame"})(),
            ),
            patch("cinepulse.aurora.subprocess.Popen", side_effect=factory),
            patch("cinepulse.aurora.popen_group_kwargs", return_value={"start_new_session": True}),
        ):
            aurora.render_reactive_intermediate(
                "ffmpeg",
                "master.mp4",
                "audio.wav",
                "out.mp4",
                1.0,
                progress.append,
                lambda: False,
                changed.append,
            )

        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(captured["start_new_session"])
        self.assertEqual(process, changed[0])
        self.assertIsNone(changed[-1])
        self.assertEqual(1.0, progress[-1])

    def test_reader_thread_start_failure_reaps_process_and_closes_pipes(self) -> None:
        process = _FakeProcess(returncode=0, running=True)
        changed = []

        def terminate(target, *_args, **_kwargs):
            target._running = False

        with (
            patch("cinepulse.aurora._decode_audio", return_value=np.zeros(16, dtype=np.float32)),
            patch("cinepulse.aurora._analyze_audio", return_value=self._analysis()),
            patch(
                "cinepulse.aurora.AuroraFrameGenerator",
                return_value=type("Generator", (), {"make": lambda self, *_args: b"frame"})(),
            ),
            patch("cinepulse.aurora.subprocess.Popen", return_value=process),
            patch("cinepulse.aurora.threading.Thread.start", side_effect=RuntimeError("thread start failed")),
            patch("cinepulse.aurora.terminate_process_tree", side_effect=terminate) as kill,
        ):
            with self.assertRaisesRegex(RuntimeError, "thread start failed"):
                aurora.render_reactive_intermediate(
                    "ffmpeg", "master.mp4", "audio.wav", "out.mp4", 1.0,
                    lambda _value: None, lambda: False, changed.append,
                )

        kill.assert_called_once()
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertIsNone(changed[-1])

    def test_cancellation_terminates_tree_and_closes_pipes(self) -> None:
        process = _FakeProcess(returncode=0, running=True)
        changed = []
        states = iter((False, False, True))

        with (
            patch("cinepulse.aurora._decode_audio", return_value=np.zeros(16, dtype=np.float32)),
            patch("cinepulse.aurora._analyze_audio", return_value=self._analysis()),
            patch(
                "cinepulse.aurora.AuroraFrameGenerator",
                return_value=type("Generator", (), {"make": lambda self, *_args: b"frame"})(),
            ),
            patch("cinepulse.aurora.subprocess.Popen", return_value=process),
            patch("cinepulse.aurora.terminate_process_tree") as terminate,
        ):
            with self.assertRaises(aurora.RenderCancelled):
                aurora.render_reactive_intermediate(
                    "ffmpeg",
                    "master.mp4",
                    "audio.wav",
                    "out.mp4",
                    1.0,
                    lambda _value: None,
                    lambda: next(states),
                    changed.append,
                )

        self.assertGreaterEqual(terminate.call_count, 1)
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertIsNone(changed[-1])


if __name__ == "__main__":
    unittest.main()
