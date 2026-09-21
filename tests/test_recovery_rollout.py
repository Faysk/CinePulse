from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.recovery_rollout import flags_for_ring, load_recovery_flags, rollback_to_shadow, write_ring


class RecoveryRolloutTests(unittest.TestCase):
    def test_ring_progression_is_conservative(self) -> None:
        self.assertFalse(flags_for_ring(1).recovery_worker)
        self.assertTrue(flags_for_ring(2).recovery_worker)
        self.assertFalse(flags_for_ring(2).recovery_discovery)
        self.assertTrue(flags_for_ring(3).recovery_discovery)
        self.assertFalse(flags_for_ring(4).recovery_cleanup_ui)
        self.assertTrue(flags_for_ring(5).recovery_cleanup_ui)

    def test_file_and_environment_overrides_are_local(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "flags.json"
            write_ring(path, 1)
            with patch.dict(os.environ, {"CINEPULSE_RECOVERY_WORKER": "1"}, clear=False):
                flags = load_recovery_flags(path)
            self.assertTrue(flags.recovery_worker)
            self.assertEqual(1, flags.ring)

    def test_rollback_disables_execution_but_preserves_external_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            flags_path = root / "flags.json"
            manifest = root / "manifest.json"
            manifest.write_text('{"keep": true}', encoding="utf-8")
            write_ring(flags_path, 4)
            rolled = rollback_to_shadow(flags_path)
            self.assertEqual(1, rolled.ring)
            self.assertFalse(rolled.recovery_worker)
            self.assertFalse(rolled.recovery_discovery)
            self.assertEqual('{"keep": true}', manifest.read_text(encoding="utf-8"))
            payload = json.loads(flags_path.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["ring"])


    def test_write_ring_fsyncs_and_leaves_no_atomic_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "flags.json"
            with patch("cinepulse.recovery_rollout.os.fsync", wraps=os.fsync) as fsync:
                write_ring(path, 3)
            self.assertGreaterEqual(fsync.call_count, 1)
            self.assertEqual([], list(root.glob("flags.json.tmp-*")))
            self.assertEqual(3, load_recovery_flags(path).ring)

    def test_file_override_rejects_non_boolean_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "flags.json"
            path.write_text(
                json.dumps({"ring": 1, "recovery_worker": "false"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "deve ser booleano"):
                load_recovery_flags(path)


if __name__ == "__main__":
    unittest.main()
