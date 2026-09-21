from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cinepulse.job_lease import LeaseBusy
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

    def test_deep_contract_uses_deep_verify_before_promotion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = root / ".out.partial-1.mp4"
            final = root / "out.mp4"
            partial.write_bytes(b"valid-output")
            payload = {
                "schema": 1, "pid": 999999, "partial": str(partial), "final": str(final),
                "expected": {"width": 640, "height": 360, "fps": 30.0, "duration": 2.0,
                             "expect_audio": False, "video_codec": "HEVC", "audio_codec": None,
                             "audio_channels": None, "audio_sample_rate": None, "deep": True},
            }
            studio = self._studio(payload)
            verification = SimpleNamespace(passed=True, frame_count=60, errors=())
            with (
                patch("cinepulse.studio.process_alive", return_value=False),
                patch("cinepulse.studio.FFMPEG", "ffmpeg"),
                patch("cinepulse.studio.FFPROBE", "ffprobe"),
                patch("cinepulse.studio.quick_verify") as quick,
                patch("cinepulse.studio.deep_verify", return_value=verification) as deep,
                patch("cinepulse.studio.messagebox.askyesno", return_value=False),
            ):
                studio._recover_interrupted_render()
            quick.assert_not_called()
            deep.assert_called_once()
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


    def test_second_instance_is_blocked_before_journal_or_worker_start(self):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        studio._render_lease = MagicMock()
        studio._render_lease.acquire.side_effect = LeaseBusy("owned")
        studio._render_journal = MagicMock()
        studio._set_feedback = MagicMock()

        started = studio._launch_worker(MagicMock(), False)

        self.assertFalse(started)
        studio._render_lease.acquire.assert_called_once_with(phase="render")
        studio._render_journal.claim.assert_not_called()
        self.assertEqual("warning", studio._set_feedback.call_args.args[0])

    def test_journal_claim_failure_releases_cross_process_ownership(self):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        studio._render_lease = MagicMock()
        studio._render_lease.nonce = "owned"
        studio._render_journal = MagicMock()
        studio._render_journal.claim.side_effect = OSError("disk full")
        studio._set_feedback = MagicMock()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("cinepulse.studio.PATHS", SimpleNamespace(locks=root)):
                started = studio._launch_worker(MagicMock(), True)

        self.assertFalse(started)
        studio._render_lease.acquire.assert_called_once_with(phase="preview")
        studio._render_lease.release.assert_called_once()
        self.assertEqual("error", studio._set_feedback.call_args.args[0])

    def test_release_render_ownership_cleans_released_evidence(self):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        studio._render_lease = MagicMock()
        studio._render_lease.nonce = "owned"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "render-owner.json.released-1-deadbeef"
            evidence.write_text("released", encoding="utf-8")
            with patch("cinepulse.studio.PATHS", SimpleNamespace(locks=root)):
                error = studio._release_render_ownership()
            self.assertEqual("", error)
            self.assertFalse(evidence.exists())
        studio._render_lease.release.assert_called_once()

    def test_legacy_render_lock_writer_delegates_to_durable_journal_claim(self):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        studio._render_journal = MagicMock()
        studio._write_render_lock(True)
        studio._render_journal.claim.assert_called_once_with(True)


    def test_live_foreign_owner_blocks_new_render_without_touching_journal(self):
        studio = self._studio({"schema": 1, "pid": 222})
        with patch("cinepulse.studio.process_alive", return_value=True):
            allowed = studio._prepare_preserved_render_for_new_run()
        self.assertFalse(allowed)
        studio._render_journal.clear.assert_not_called()
        self.assertEqual("warning", studio._set_feedback.call_args.args[0])

    def test_stale_minimal_owner_record_is_cleared_before_new_render(self):
        studio = self._studio({"schema": 1, "pid": 999999, "preview": False})
        with patch("cinepulse.studio.process_alive", return_value=False):
            allowed = studio._prepare_preserved_render_for_new_run()
        self.assertTrue(allowed)
        studio._render_journal.clear.assert_called_once()

    def test_preserved_partial_survives_when_user_refuses_recovery_and_discard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = root / ".out.partial-1.mp4"
            final = root / "out.mp4"
            partial.write_bytes(b"candidate")
            payload = {
                "schema": 1,
                "pid": 999999,
                "partial": str(partial),
                "final": str(final),
                "expected": {},
            }
            studio = self._studio(payload)
            # Recovery attempt leaves the journal untouched, simulating either
            # failed validation or the user declining promotion.
            studio._recover_interrupted_render = MagicMock()
            studio._render_journal.read.side_effect = [payload, payload]
            with (
                patch("cinepulse.studio.process_alive", return_value=False),
                patch("cinepulse.studio.messagebox.askyesno", return_value=False),
                patch("cinepulse.studio.AtomicOutput.discard") as discard,
            ):
                allowed = studio._prepare_preserved_render_for_new_run()
            self.assertFalse(allowed)
            discard.assert_not_called()
            studio._render_journal.clear.assert_not_called()
            self.assertTrue(partial.is_file())

    def test_explicit_discard_clears_partial_and_journal_before_new_render(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = root / ".out.partial-1.mp4"
            final = root / "out.mp4"
            partial.write_bytes(b"candidate")
            payload = {
                "schema": 1,
                "pid": 999999,
                "partial": str(partial),
                "final": str(final),
                "expected": {},
            }
            studio = self._studio(payload)
            studio._recover_interrupted_render = MagicMock()
            studio._render_journal.read.side_effect = [payload, payload]
            with (
                patch("cinepulse.studio.process_alive", return_value=False),
                patch("cinepulse.studio.messagebox.askyesno", return_value=True),
            ):
                allowed = studio._prepare_preserved_render_for_new_run()
            self.assertTrue(allowed)
            self.assertFalse(partial.exists())
            studio._render_journal.clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()
