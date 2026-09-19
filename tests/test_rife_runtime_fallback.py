from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cinepulse.rife_safe_runner import RifeExecutionPolicy, _run_native_with_rollback
from cinepulse.rife_tuning import RifeTuningKey, RifeTuningStore
from cinepulse.studio import VideoOptimizerStudio


def fake_png(width: int = 64, height: int = 36) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class RifeRuntimeFallbackTests(unittest.TestCase):
    def test_measured_failure_invalidates_and_retries_baseline_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "in"
            native = root / "native"
            incoming.mkdir()
            native.mkdir()
            for index in range(2):
                (incoming / f"{index:08d}.png").write_bytes(fake_png())

            key = RifeTuningKey("RTX Test", 8192, "999.1", "rife-v4.6", 3840, 2160)
            store = RifeTuningStore(root / "rife-tuning.json")
            # Seed an exact-key record using the store's atomic format.
            from cinepulse.rife_tuning import RifePolicy, RifeSample
            tuned = RifePolicy("1:2:1")
            fallback_policy = RifePolicy("1:1:1")
            store.record_samples(
                key,
                (
                    RifeSample(fallback_policy, 10.0, True, output_frames=4, expected_frames=4),
                    RifeSample(tuned, 6.0, True, output_frames=4, expected_frames=4),
                ),
                fallback=fallback_policy,
            )
            self.assertEqual(store.lookup(key), tuned)

            measured = RifeExecutionPolicy(True, "1:2:1", 4, 4, 0, True)
            fallback = RifeExecutionPolicy(True, "1:1:1", 4, 4, 0, False)
            calls = []

            def fake_run(command, **_kwargs):
                jobs = command[command.index("-j") + 1]
                calls.append(jobs)
                if jobs == "1:2:1":
                    raise RuntimeError("VK_ERROR_OUT_OF_DEVICE_MEMORY")
                for index in range(4):
                    (native / f"{index:08d}.png").write_bytes(fake_png())

            with patch("cinepulse.rife_safe_runner._run", side_effect=fake_run):
                applied = _run_native_with_rollback(
                    rife_executable=root / "rife.exe",
                    model=root / "rife-v4.6",
                    incoming=incoming,
                    native_dir=native,
                    policy=measured,
                    fallback=fallback,
                    tuning_key=key,
                    tuning_store=store,
                )
            self.assertEqual(applied.jobs, "1:1:1")
            self.assertEqual(calls, ["1:2:1", "1:1:1"])
            self.assertIsNone(store.lookup(key))

    def test_studio_rife_aborts_on_short_source_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rife_exe = root / "rife.exe"
            rife_exe.write_bytes(b"x")
            rife_model = root / "rife-v4.6"
            rife_model.mkdir()
            studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
            studio._cancelled = False
            studio._process = None
            studio._log = lambda *_args, **_kwargs: None
            studio._set_stage = lambda *_args, **_kwargs: None
            studio._push_progress = lambda *_args, **_kwargs: None

            def fake_ffmpeg(command, *_args, **_kwargs):
                requested = int(command[command.index("-frames:v") + 1])
                pattern = Path(command[-1])
                pattern.parent.mkdir(parents=True, exist_ok=True)
                # Reproduce the regression: FFmpeg exits successfully but the
                # chunk contains one fewer frame than requested.
                for index in range(max(0, requested - 1)):
                    (pattern.parent / f"{index:08d}.png").write_bytes(b"x")

            studio._run_ffmpeg = fake_ffmpeg
            color_plan = SimpleNamespace(working_pix_fmt="yuv420p")
            with (
                patch("cinepulse.studio.RIFE_EXE", rife_exe),
                patch("cinepulse.studio.RIFE_MODEL", rife_model),
                patch("cinepulse.studio.probe_media", return_value={}),
                patch("cinepulse.studio.first_video_size", return_value=(64, 36)),
                patch("cinepulse.studio.choose_chunk_frames", return_value=4),
            ):
                with self.assertRaisesRegex(RuntimeError, "extração incompleta"):
                    studio._interpolate_rife(
                        "input.mp4",
                        root,
                        0.0,
                        1.0,
                        8.0,
                        16.0,
                        False,
                        4,
                        [],
                        0.0,
                        100.0,
                        color_plan=color_plan,
                    )

    def test_baseline_failure_is_not_retried_forever(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "in"
            native = root / "native"
            incoming.mkdir()
            native.mkdir()
            for index in range(2):
                (incoming / f"{index:08d}.png").write_bytes(fake_png())
            fallback = RifeExecutionPolicy(True, "1:1:1", 4, 4, 0, False)
            with patch("cinepulse.rife_safe_runner._run", side_effect=RuntimeError("native failure")) as runner:
                with self.assertRaises(RuntimeError):
                    _run_native_with_rollback(
                        rife_executable=root / "rife.exe",
                        model=root / "rife-v4.6",
                        incoming=incoming,
                        native_dir=native,
                        policy=fallback,
                        fallback=fallback,
                        tuning_key=None,
                        tuning_store=None,
                    )
            self.assertEqual(runner.call_count, 1)


if __name__ == "__main__":
    unittest.main()
