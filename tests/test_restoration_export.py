from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from cinepulse.restoration_export import (
    PreviewExportCancelled,
    ensure_preview_scratch_capacity,
    export_preview_restoration,
    temporary_preview_output,
    validate_preview_output_contract,
)
from cinepulse.restoration_temporal_export import PreviewVideoGeometry
from cinepulse.restoration_overlay import OverlayRegion
from cinepulse.restoration_preview import PreviewRestorationPlan


EMPTY_PLAN = PreviewRestorationPlan(evidence=(), regions=(), overlay_filter="", color_filter="")


class _FakeProcess:
    def __init__(self, command, *, returncode=0, create_output=True, finish_after=1):
        self.command = command
        self.returncode = None
        self._final_returncode = returncode
        self._polls = 0
        self._finish_after = finish_after
        self._create_output = create_output
        self.terminated = False
        self.killed = False

    def poll(self):
        self._polls += 1
        if self.returncode is None and self._polls >= self._finish_after:
            self.returncode = self._final_returncode
            if self._create_output and self.returncode == 0:
                Path(self.command[-1]).write_bytes(b"preview")
        return self.returncode

    def communicate(self):
        return ("", "fake ffmpeg failure")

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = -15
        return self.returncode


class RestorationExportTests(unittest.TestCase):
    def source_contract(self) -> PreviewVideoGeometry:
        return PreviewVideoGeometry(
            width=64,
            height=36,
            fps=4.0,
            nominal_fps=4.0,
            frame_count=4,
            duration=1.0,
            has_audio=True,
        )

    def test_temp_output_preserves_container_suffix(self):
        target = Path("movie.mp4")
        temp = temporary_preview_output(target)
        self.assertEqual(temp.suffix, ".mp4")
        self.assertNotEqual(temp, target)
        self.assertIn("cinepulse-preview", temp.name)

    def test_scratch_guard_rejects_obviously_full_volume(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            source.write_bytes(b"x" * 100)
            usage = type("Usage", (), {"free": 50})()
            with patch("cinepulse.restoration_export.shutil.disk_usage", return_value=usage):
                with self.assertRaises(OSError):
                    ensure_preview_scratch_capacity(source, root, minimum_free_bytes=60, source_multiplier=0)

    def test_success_promotes_temp_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "done.mp4"
            source.write_bytes(b"source")

            def factory(command, **_kwargs):
                return _FakeProcess(command)

            with (
                patch("cinepulse.restoration_export.ensure_preview_scratch_capacity", return_value=0),
                patch("cinepulse.restoration_export.probe_preview_geometry", return_value=self.source_contract()),
                patch("cinepulse.restoration_export.validate_preview_output_contract", return_value=self.source_contract()) as validate,
                patch("cinepulse.restoration_export.subprocess.Popen", side_effect=factory),
            ):
                result = export_preview_restoration(
                    "ffmpeg", source, output, EMPTY_PLAN, ffprobe="ffprobe", poll_interval=0.001
                )

            validate.assert_called_once()

            self.assertEqual(result.output, output)
            self.assertEqual(output.read_bytes(), b"preview")
            self.assertEqual(list(root.glob(".*cinepulse-preview*")), [])

    def test_failure_removes_partial_temp_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "done.mp4"
            source.write_bytes(b"source")
            output.write_bytes(b"old-good")

            def factory(command, **_kwargs):
                Path(command[-1]).write_bytes(b"partial")
                return _FakeProcess(command, returncode=1, create_output=False)

            with (
                patch("cinepulse.restoration_export.ensure_preview_scratch_capacity", return_value=0),
                patch("cinepulse.restoration_export.probe_preview_geometry", return_value=self.source_contract()),
                patch("cinepulse.restoration_export.subprocess.Popen", side_effect=factory),
            ):
                with self.assertRaises(RuntimeError):
                    export_preview_restoration(
                        "ffmpeg", source, output, EMPTY_PLAN, ffprobe="ffprobe", poll_interval=0.001
                    )

            self.assertEqual(output.read_bytes(), b"old-good")
            self.assertEqual(list(root.glob(".*cinepulse-preview*")), [])

    def test_cancel_terminates_process_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "done.mp4"
            source.write_bytes(b"source")
            cancel = threading.Event()
            holder = {}

            def factory(command, **_kwargs):
                process = _FakeProcess(command, finish_after=999)
                Path(command[-1]).write_bytes(b"partial")
                holder["process"] = process
                cancel.set()
                return process

            with (
                patch("cinepulse.restoration_export.ensure_preview_scratch_capacity", return_value=0),
                patch("cinepulse.restoration_export.probe_preview_geometry", return_value=self.source_contract()),
                patch("cinepulse.restoration_export.subprocess.Popen", side_effect=factory),
            ):
                with self.assertRaises(PreviewExportCancelled):
                    export_preview_restoration(
                        "ffmpeg", source, output, EMPTY_PLAN,
                        ffprobe="ffprobe", cancel_event=cancel, poll_interval=0.001
                    )

            self.assertTrue(holder["process"].terminated)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".*cinepulse-preview*")), [])

    def test_missing_ffprobe_fails_before_output_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "done.mp4"
            source.write_bytes(b"source")
            output.write_bytes(b"old-good")
            with self.assertRaisesRegex(ValueError, "FFprobe"):
                export_preview_restoration("ffmpeg", source, output, EMPTY_PLAN)
            self.assertEqual(b"old-good", output.read_bytes())

    def test_validation_failure_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.mp4"
            output = root / "done.mp4"
            source.write_bytes(b"source")
            output.write_bytes(b"old-good")

            def factory(command, **_kwargs):
                return _FakeProcess(command)

            with (
                patch("cinepulse.restoration_export.ensure_preview_scratch_capacity", return_value=0),
                patch("cinepulse.restoration_export.probe_preview_geometry", return_value=self.source_contract()),
                patch(
                    "cinepulse.restoration_export.validate_preview_output_contract",
                    side_effect=RuntimeError("frame mismatch"),
                ),
                patch("cinepulse.restoration_export.subprocess.Popen", side_effect=factory),
            ):
                with self.assertRaisesRegex(RuntimeError, "frame mismatch"):
                    export_preview_restoration(
                        "ffmpeg", source, output, EMPTY_PLAN,
                        ffprobe="ffprobe", poll_interval=0.001,
                    )

            self.assertEqual(b"old-good", output.read_bytes())
            self.assertEqual(list(root.glob(".*cinepulse-preview*")), [])

    def test_output_contract_rejects_frame_or_audio_drift(self):
        source = self.source_contract()
        candidate = PreviewVideoGeometry(
            width=64,
            height=36,
            fps=4.0,
            nominal_fps=4.0,
            frame_count=3,
            duration=0.75,
            has_audio=False,
        )
        with patch("cinepulse.restoration_export.probe_preview_geometry", return_value=candidate):
            with self.assertRaisesRegex(RuntimeError, "video frames"):
                validate_preview_output_contract(
                    "ffprobe", source, Path("candidate.mp4"), expected_frames=4
                )

    def test_output_contract_accepts_exact_temporal_candidate(self):
        source = self.source_contract()
        with patch("cinepulse.restoration_export.probe_preview_geometry", return_value=source):
            result = validate_preview_output_contract(
                "ffprobe",
                source,
                Path("candidate.mp4"),
                expected_frames=4,
                require_cfr=True,
            )
        self.assertEqual(source, result)

    def test_source_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.mp4"
            source.write_bytes(b"source")
            with self.assertRaises(ValueError):
                export_preview_restoration("ffmpeg", source, source, EMPTY_PLAN)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe required")
class RestorationExportFfmpegIntegrationTests(unittest.TestCase):
    def test_short_audio_does_not_truncate_temporal_video(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
            ffprobe = shutil.which("ffprobe") or "ffprobe"
            source = root / "source.mkv"
            output = root / "restored.mkv"
            subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc2=size=64x36:rate=4:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.5",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "ffv1", "-c:a", "pcm_s16le",
                    str(source),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            plan = PreviewRestorationPlan(
                evidence=(),
                regions=(OverlayRegion(x=0.2, y=0.2, width=0.2, height=0.2),),
                overlay_filter="",
                color_filter="",
            )
            result = export_preview_restoration(
                ffmpeg,
                source,
                output,
                plan,
                ffprobe=ffprobe,
                poll_interval=0.001,
            )
            self.assertTrue(result.used_temporal_reconstruction)
            self.assertEqual(4, result.temporal_frames)
            probe = subprocess.run(
                [
                    ffprobe, "-v", "error", "-count_frames", "-show_entries",
                    "stream=codec_type,nb_read_frames", "-of", "json", str(output),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            import json
            payload = json.loads(probe.stdout)
            video = next(item for item in payload["streams"] if item["codec_type"] == "video")
            self.assertEqual("4", video["nb_read_frames"])


if __name__ == "__main__":
    unittest.main()
