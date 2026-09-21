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

    def test_discard_retries_transient_windows_style_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atomic = AtomicOutput.for_path(Path(temporary) / "video.mp4", pid=123)
            atomic.prepare().write_bytes(b"partial")
            real_unlink = Path.unlink
            attempts = 0

            def transient(path: Path, *args, **kwargs):
                nonlocal attempts
                if path == atomic.partial:
                    attempts += 1
                    if attempts < 3:
                        raise PermissionError("sharing violation")
                return real_unlink(path, *args, **kwargs)

            with patch("pathlib.Path.unlink", autospec=True, side_effect=transient):
                atomic.discard(timeout_seconds=0.5, retry_seconds=0.001)
            self.assertEqual(3, attempts)
            self.assertFalse(atomic.partial.exists())

    def test_discard_persistent_permission_error_still_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            atomic = AtomicOutput.for_path(Path(temporary) / "video.mp4", pid=123)
            atomic.prepare().write_bytes(b"partial")
            with patch("pathlib.Path.unlink", autospec=True, side_effect=PermissionError("still locked")):
                with self.assertRaises(PermissionError):
                    atomic.discard(timeout_seconds=0.0, retry_seconds=0.001)
            self.assertTrue(atomic.partial.exists())

    def test_permission_error_means_process_may_still_be_alive(self) -> None:
        with patch("cinepulse.safe_output.os.kill", side_effect=PermissionError("denied")):
            self.assertTrue(process_alive(1234))

    def test_missing_process_is_dead(self) -> None:
        with patch("cinepulse.safe_output.os.kill", side_effect=ProcessLookupError("gone")):
            self.assertFalse(process_alive(1234))

    def test_journal_write_is_fsynced_and_leaves_no_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            atomic = AtomicOutput.for_path(root / "final.mp4", pid=42)
            journal = RenderJournal(root / "render.json")
            with patch("cinepulse.safe_output.os.fsync", wraps=__import__("os").fsync) as fsync:
                journal.write(atomic, preview=False, expected={"fps": 60})
            self.assertGreaterEqual(fsync.call_count, 1)
            self.assertEqual([], list(root.glob("render.json.tmp-*")))
            self.assertEqual(60, journal.read()["expected"]["fps"])

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


    def test_initial_owner_claim_is_fsynced_and_contains_no_output_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = RenderJournal(root / "render.json")
            with patch("cinepulse.safe_output.os.fsync", wraps=__import__("os").fsync) as fsync:
                journal.claim(preview=True)
            payload = journal.read()
            self.assertEqual(1, payload["schema"])
            self.assertTrue(payload["preview"])
            self.assertGreater(payload["pid"], 0)
            self.assertNotIn("partial", payload)
            self.assertNotIn("final", payload)
            self.assertGreaterEqual(fsync.call_count, 1)
            self.assertEqual([], list(root.glob("render.json.tmp-*")))

    def test_clear_removes_durable_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = RenderJournal(root / "render.json")
            journal.claim(preview=False)
            self.assertTrue(journal.path.is_file())
            journal.clear()
            self.assertFalse(journal.path.exists())


    def test_non_object_journal_is_treated_as_invalid_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            journal = RenderJournal(root / "render.json")
            journal.path.write_text("[]", encoding="utf-8")
            self.assertIsNone(journal.read())


    def test_commit_fsyncs_verified_partial_before_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            final = root / "video.mp4"
            final.write_bytes(b"old")
            atomic = AtomicOutput.for_path(final, pid=123)
            atomic.prepare().write_bytes(b"new-video")
            real_replace = __import__("os").replace
            events: list[str] = []

            def observed_replace(source, destination):
                if Path(source) == atomic.partial and Path(destination) == atomic.final:
                    events.append("replace")
                return real_replace(source, destination)

            with (
                patch("cinepulse.safe_output.os.fsync", wraps=__import__("os").fsync) as fsync,
                patch("cinepulse.safe_output.os.replace", side_effect=observed_replace),
            ):
                atomic.commit()
            self.assertGreaterEqual(fsync.call_count, 1)
            self.assertEqual(["replace"], events)
            self.assertEqual(b"new-video", final.read_bytes())

    def test_fsync_failure_keeps_previous_final_and_recoverable_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            final = Path(temporary) / "video.mp4"
            final.write_bytes(b"old")
            atomic = AtomicOutput.for_path(final, pid=123)
            atomic.prepare().write_bytes(b"new-video")

            with patch("cinepulse.safe_output.os.fsync", side_effect=OSError("disk flush failed")):
                with self.assertRaisesRegex(OSError, "disk flush failed"):
                    atomic.commit()

            self.assertEqual(b"old", final.read_bytes())
            self.assertEqual(b"new-video", atomic.partial.read_bytes())


if __name__ == "__main__":
    unittest.main()
