from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cinepulse.studio import VideoOptimizerStudio


class InterruptedRenderRecoveryTests(unittest.TestCase):
    def _studio(self, payload):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        studio._render_journal = MagicMock()
        studio._render_journal.read.return_value = payload
        studio._set_feedback = MagicMock()
        studio._show_log = MagicMock()
        studio._open_external_path = MagicMock()
        return studio

    def test_invalid_partial_is_preserved_and_never_offered_for_promotion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = root / ".out.partial-1.mp4"
            final = root / "out.mp4"
            partial.write_bytes(b"playable-looking")
            payload = {
                "schema": 1, "pid": 999999, "partial": str(partial), "final": str(final),
                "expected": {"width": 640, "height": 360, "fps": 30.0, "duration": 2.0,
                             "expect_audio": True, "video_codec": "HEVC", "audio_codec": "AAC",
                             "audio_channels": 2, "audio_sample_rate": 48000},
            }
            studio = self._studio(payload)
            verification = SimpleNamespace(
                passed=False, frame_count=59,
                errors=(SimpleNamespace(code="VERIFY-FRAMES", message="59/60"),),
            )
            with (
                patch("cinepulse.studio.process_alive", return_value=False),
                patch("cinepulse.studio.FFPROBE", "ffprobe"),
                patch("cinepulse.studio.quick_verify", return_value=verification),
                patch("cinepulse.studio.messagebox.askyesno") as ask,
                patch("cinepulse.studio.AtomicOutput.commit") as commit,
            ):
                studio._recover_interrupted_render()
            ask.assert_not_called()
            commit.assert_not_called()
            studio._render_journal.clear.assert_not_called()
            self.assertTrue(partial.is_file())
            self.assertIn("VERIFY-FRAMES", studio._set_feedback.call_args.kwargs["technical_detail"])

    def test_exact_partial_may_be_promoted_after_user_confirmation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = root / ".out.partial-1.mp4"
            final = root / "out.mp4"
            partial.write_bytes(b"valid-output")
            payload = {
                "schema": 1, "pid": 999999, "partial": str(partial), "final": str(final),
                "expected": {"width": 640, "height": 360, "fps": 30.0, "duration": 2.0,
                             "expect_audio": False, "video_codec": "HEVC", "audio_codec": None,
                             "audio_channels": None, "audio_sample_rate": None},
            }
            studio = self._studio(payload)
            verification = SimpleNamespace(passed=True, frame_count=60, errors=())
            with (
                patch("cinepulse.studio.process_alive", return_value=False),
                patch("cinepulse.studio.FFPROBE", "ffprobe"),
                patch("cinepulse.studio.quick_verify", return_value=verification),
                patch("cinepulse.studio.messagebox.askyesno", return_value=True),
                patch("cinepulse.studio.AtomicOutput.commit", return_value=final) as commit,
            ):
                studio._recover_interrupted_render()
            commit.assert_called_once()
            studio._render_journal.clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
