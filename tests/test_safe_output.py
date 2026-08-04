from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cinepulse.safe_output import AtomicOutput, RenderJournal


class SafeOutputTests(unittest.TestCase):
    def test_commit_replaces_existing_only_after_partial_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            final = Path(temporary) / "video.mp4"
            final.write_bytes(b"old")
            atomic = AtomicOutput.for_path(final, pid=123)
            atomic.prepare().write_bytes(b"new-video")
            self.assertEqual(final, atomic.commit())
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

