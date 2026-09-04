from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.safe_output import AtomicOutput, RenderJournal, process_alive


class SafeOutputTests(unittest.TestCase):
    def test_commit_replaces_existing_only_after_partial_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            final = Path(temporary) / "video.mp4"
            final.write_bytes(b"old")
            atomic = AtomicOutput.for_path(final, pid=123)
            atomic.prepare().write_bytes(b"new-video")
            self.assertEqual(atomic.final, atomic.commit())
            self.assertEqual(b"new-video", final.read_bytes())
            self.assertFalse(atomic.partial.exists())
            self.assertFalse(atomic.backup.exists())

    def test_missing_partial_keeps_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            final = Path(temporary) / "video.mp4"
            final.write_bytes(b"old")
            atomic = AtomicOutput.for_path(final, pid=123)
            with self.assertRaises(RuntimeError):
                atomic.commit()
            self.assertEqual(b"old", final.read_bytes())

    def test_replace_failure_keeps_previous_final_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            final = Path(temporary) / "video.mp4"
            final.write_bytes(b"old")
            atomic = AtomicOutput.for_path(final, pid=123)
            atomic.prepare().write_bytes(b"new-video")
            real_replace = __import__("os").replace

            def fail_partial(source, destination):
                if Path(source) == atomic.partial and Path(destination) == atomic.final:
                    raise OSError("injected replace failure")
                return real_replace(source, destination)

            with patch("cinepulse.safe_output.os.replace", side_effect=fail_partial):
                with self.assertRaises(OSError):
                    atomic.commit()
            self.assertEqual(b"old", final.read_bytes())
            self.assertEqual(b"new-video", atomic.partial.read_bytes())

    def test_stale_legacy_backup_is_removed_before_atomic_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            final = Path(temporary) / "video.mp4"
            final.write_bytes(b"old")
            atomic = AtomicOutput.for_path(final, pid=123)
            atomic.backup.write_bytes(b"stale")
            atomic.prepare().write_bytes(b"new")
            atomic.commit()
            self.assertFalse(atomic.backup.exists())
            self.assertEqual(b"new", final.read_bytes())

    def test_permission_error_means_process_may_still_be_alive(self) -> None:
        with patch("cinepulse.safe_output.os.kill", side_effect=PermissionError("denied")):
            self.assertTrue(process_alive(1234))

    def test_missing_process_is_dead(self) -> None:
        with patch("cinepulse.safe_output.os.kill", side_effect=ProcessLookupError("gone")):
            self.assertFalse(process_alive(1234))

    def test_journal_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic = AtomicOutput.for_path(root / "final.mp4", pid=42)
            journal = RenderJournal(root / "render.json")
            journal.write(atomic, preview=False, expected={"fps": 60})
            payload = journal.read()
            self.assertEqual(60, payload["expected"]["fps"])
            journal.clear()
            self.assertIsNone(journal.read())


if __name__ == "__main__":
    unittest.main()
