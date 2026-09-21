from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from cinepulse.studio import VideoOptimizerStudio


class PostCommitStateIsolationTests(unittest.TestCase):
    def _studio(self):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        studio._log = MagicMock()
        studio._render_journal = MagicMock()
        return studio

    def test_history_verification_failure_is_warning_not_exception(self) -> None:
        studio = self._studio()
        history = MagicMock()
        history.write_verification.side_effect = OSError("history disk full")
        self.assertFalse(studio._history_write_verification_safely(history, {"passed": True}))
        studio._log.assert_called_once()
        self.assertIn("HISTORY WARNING", studio._log.call_args.args[0])

    def test_history_finish_failure_is_warning_not_exception(self) -> None:
        studio = self._studio()
        history = MagicMock()
        history.finish.side_effect = OSError("history unavailable")
        self.assertFalse(
            studio._history_finish_safely(
                history,
                "success",
                output=Path("final.mp4"),
                report=Path("report.json"),
            )
        )
        studio._log.assert_called_once()
        self.assertIn("HISTORY WARNING", studio._log.call_args.args[0])

    def test_quality_report_failure_after_commit_returns_empty_report(self) -> None:
        studio = self._studio()
        studio._write_quality_report = MagicMock(side_effect=OSError("report disk full"))
        report = studio._write_quality_report_safely(
            Path("final.mp4"),
            MagicMock(),
            MagicMock(),
            10.0,
            render_plan=MagicMock(),
        )
        self.assertEqual("", report)
        studio._log.assert_called_once()
        self.assertIn("REPORT WARNING", studio._log.call_args.args[0])

    def test_journal_cleanup_failure_after_commit_is_warning(self) -> None:
        studio = self._studio()
        studio._render_journal.clear.side_effect = PermissionError("locked")
        self.assertFalse(studio._clear_render_journal_safely("após promoção final"))
        studio._log.assert_called_once()
        self.assertIn("RECOVERY WARNING", studio._log.call_args.args[0])

    def test_worker_uses_nonfatal_support_metadata_helpers(self) -> None:
        source = inspect.getsource(VideoOptimizerStudio._worker)
        self.assertIn("_history_write_verification_safely", source)
        self.assertIn("_history_finish_safely", source)
        self.assertIn("_write_quality_report_safely", source)
        self.assertIn("_clear_render_journal_safely", source)
        self.assertNotIn('history.finish("success"', source)
        self.assertNotIn('history.finish("error"', source)
        self.assertNotIn('history.finish("cancelled"', source)


if __name__ == "__main__":
    unittest.main()
