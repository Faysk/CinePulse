from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cinepulse.studio import VideoOptimizerStudio


class AuxiliaryEncoderFallbackTests(unittest.TestCase):
    def test_transition_non_gpu_failure_is_not_retried_on_cpu(self) -> None:
        app = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        app._nvenc = True
        app._hardware = SimpleNamespace(gpu_index=2)
        app._set_stage = lambda *args, **kwargs: None
        app._log = lambda _line: None
        calls: list[list[str]] = []

        def fake_run(command, *args, **kwargs):
            calls.append(list(command))
            raise RuntimeError("No space left on device")

        app._run_ffmpeg = fake_run
        color_plan = SimpleNamespace(
            needs_lossless_intermediate=False,
            working_pix_fmt="yuv420p",
            metadata_args=lambda output=False: [],
            setparams_filter=lambda: (
                "setparams=range=limited:color_primaries=bt709:"
                "color_trc=bt709:colorspace=bt709"
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "No space left on device"):
            VideoOptimizerStudio._create_transition(
                app,
                "master.mp4",
                Path("transition.mp4"),
                2.0,
                "Dissolver suave",
                0.5,
                1920,
                1080,
                False,
                0.0,
                1.0,
                8,
                color_plan,
            )

        self.assertEqual(1, len(calls))

    def test_transition_retries_h264_nvenc_failure_with_libx264(self) -> None:
        app = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        app._nvenc = True
        app._hardware = SimpleNamespace(gpu_index=2)
        app._set_stage = lambda *args, **kwargs: None
        logs: list[str] = []
        app._log = logs.append

        calls: list[list[str]] = []

        def fake_run(command, *args, **kwargs):
            calls.append(list(command))
            if len(calls) == 1:
                raise RuntimeError("synthetic NVENC failure")

        app._run_ffmpeg = fake_run
        color_plan = SimpleNamespace(
            needs_lossless_intermediate=False,
            working_pix_fmt="yuv420p",
            metadata_args=lambda output=False: [],
            setparams_filter=lambda: (
                "setparams=range=limited:color_primaries=bt709:"
                "color_trc=bt709:colorspace=bt709"
            ),
        )

        with patch.object(Path, "unlink", return_value=None):
            result = VideoOptimizerStudio._create_transition(
                app,
                "master.mp4",
                Path("transition.mp4"),
                2.0,
                "Dissolver suave",
                0.5,
                1920,
                1080,
                False,
                0.0,
                1.0,
                8,
                color_plan,
            )

        self.assertEqual("transition.mp4", result)
        self.assertEqual(2, len(calls))
        self.assertEqual("h264_nvenc", calls[0][calls[0].index("-c:v") + 1])
        self.assertEqual("2", calls[0][calls[0].index("-gpu") + 1])
        self.assertEqual("libx264", calls[1][calls[1].index("-c:v") + 1])
        self.assertNotIn("-gpu", calls[1])
        self.assertTrue(any("repetindo com libx264" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
