from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cinepulse.studio import VideoOptimizerStudio


class ComparisonPreviewContractTests(unittest.TestCase):
    def test_auxiliary_nvenc_failure_retries_comparison_with_cpu(self) -> None:
        app = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        app._nvenc = True
        app._hardware = SimpleNamespace(gpu_index=2)
        app._set_stage = lambda *args, **kwargs: None
        logs: list[str] = []
        app._log = logs.append

        captured: list[list[str]] = []

        def capture(command, *args, **kwargs):
            captured.append(list(command))
            if len(captured) == 1:
                raise RuntimeError("NVENC auxiliary failure")

        app._run_ffmpeg = capture
        settings = SimpleNamespace(
            mode="Vídeo",
            video="source.mp4",
            use_cpu=False,
        )
        probe = {
            "streams": [
                {"codec_type": "video", "avg_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        }

        with (
            patch("cinepulse.studio.probe_media", return_value=probe),
            patch("cinepulse.studio.first_video_fps", return_value=30.0),
            patch.object(Path, "unlink", return_value=None),
        ):
            result = VideoOptimizerStudio._create_comparison_preview(
                app,
                Path("processed.mp4"),
                settings,
                31 / 30,
                0.0,
                8,
            )

        self.assertEqual(Path("processed_COMPARACAO.mp4"), result)
        self.assertEqual(2, len(captured))
        self.assertEqual("h264_nvenc", captured[0][captured[0].index("-c:v") + 1])
        self.assertEqual("libx264", captured[1][captured[1].index("-c:v") + 1])
        self.assertNotIn("-gpu", captured[1])
        self.assertTrue(any("repetindo com libx264" in line for line in logs))

    def test_audio_and_auxiliary_nvenc_follow_exact_timeline_and_selected_gpu(self) -> None:
        app = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        app._nvenc = True
        app._hardware = SimpleNamespace(gpu_index=2)
        app._set_stage = lambda *args, **kwargs: None

        captured: list[list[str]] = []

        def capture(command, *args, **kwargs):
            captured.append(list(command))

        app._run_ffmpeg = capture
        settings = SimpleNamespace(
            mode="Vídeo",
            video="source.mp4",
            use_cpu=False,
        )
        probe = {
            "streams": [
                {"codec_type": "video", "avg_frame_rate": "30/1"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        }

        with (
            patch("cinepulse.studio.probe_media", return_value=probe),
            patch("cinepulse.studio.first_video_fps", return_value=30.0),
        ):
            result = VideoOptimizerStudio._create_comparison_preview(
                app,
                Path("processed.mp4"),
                settings,
                31 / 30,
                0.0,
                8,
            )

        self.assertEqual(Path("processed_COMPARACAO.mp4"), result)
        self.assertEqual(1, len(captured))
        command = captured[0]

        self.assertEqual("h264_nvenc", command[command.index("-c:v") + 1])
        self.assertEqual("2", command[command.index("-gpu") + 1])
        self.assertIn("[aout]", command)
        self.assertEqual("aac", command[command.index("-c:a") + 1])
        self.assertNotIn("copy", command)
        self.assertEqual("31", command[command.index("-frames:v") + 1])

        graph = command[command.index("-filter_complex") + 1]
        self.assertIn("atrim=duration=1.033333333333", graph)
        self.assertIn("apad=whole_dur=1.033333333333", graph)


if __name__ == "__main__":
    unittest.main()
