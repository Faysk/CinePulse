from __future__ import annotations

import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest import mock

from cinepulse.state_store import (
    PRESETS_SCHEMA,
    QUEUE_SCHEMA,
    load_presets_state,
    load_queue_state,
    save_presets_state,
    save_queue_state,
)


class StateStoreTests(TestCase):
    def test_legacy_queue_list_is_migratable(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            path.write_text(json.dumps([{"id": 1}]), encoding="utf-8")
            items, migrated = load_queue_state(path)
            self.assertTrue(migrated)
            self.assertEqual(items[0]["id"], 1)

    def test_queue_save_is_versioned_and_backed_up(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            path.write_text("[]", encoding="utf-8")
            save_queue_state(path, [{"id": 2}])
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], QUEUE_SCHEMA)
            self.assertEqual(payload["kind"], "cinepulse.queue")
            self.assertEqual(payload["items"][0]["id"], 2)
            self.assertTrue(path.with_suffix(".json.bak").is_file())

    def test_concurrent_queue_saves_use_independent_atomic_temps(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "queue.json"
            save_queue_state(path, [{"id": 0}])
            errors: list[BaseException] = []

            def writer(value: int) -> None:
                try:
                    save_queue_state(path, [{"id": value}])
                except BaseException as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(value,)) for value in range(1, 9)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)

            self.assertFalse(errors)
            primary = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("cinepulse.queue", primary["kind"])
            self.assertIn(primary["items"][0]["id"], range(1, 9))
            backup = path.with_suffix(".json.bak")
            self.assertTrue(backup.is_file())
            json.loads(backup.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob("queue.json.tmp-*")))
            self.assertEqual([], list(root.glob("queue.json.bak.tmp-*")))

    def test_queue_save_flushes_state_before_atomic_promotion(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            with mock.patch("cinepulse.state_store.os.fsync", wraps=__import__("os").fsync) as fsync:
                save_queue_state(path, [{"id": 1}])
            self.assertGreaterEqual(fsync.call_count, 1)
            self.assertEqual(1, json.loads(path.read_text(encoding="utf-8"))["items"][0]["id"])

    def test_corrupt_queue_recovers_validated_backup_and_preserves_evidence(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            backup = path.with_suffix(".json.bak")
            backup.write_text(
                json.dumps({"schema": QUEUE_SCHEMA, "kind": "cinepulse.queue", "items": [{"id": 7}]}),
                encoding="utf-8",
            )
            path.write_text('{"broken":', encoding="utf-8")
            items, migrated = load_queue_state(path)
            self.assertTrue(migrated)
            self.assertEqual(items, [{"id": 7}])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["items"][0]["id"], 7)
            self.assertTrue(list(Path(temp).glob("queue.json.corrupt-*")))

    def test_future_queue_schema_is_rejected_even_with_older_backup(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            path.write_text(json.dumps({"schema": 999, "kind": "cinepulse.queue", "items": []}), encoding="utf-8")
            path.with_suffix(".json.bak").write_text(
                json.dumps({"schema": QUEUE_SCHEMA, "kind": "cinepulse.queue", "items": [{"id": 1}]}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_queue_state(path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], 999)

    def test_legacy_presets_dict_is_migratable(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.write_text(json.dumps({"Meu preset": {"fps": 60}}), encoding="utf-8")
            presets, migrated = load_presets_state(path)
            self.assertTrue(migrated)
            self.assertEqual(presets["Meu preset"]["fps"], 60)

    def test_presets_save_is_versioned_and_backed_up(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.write_text("{}", encoding="utf-8")
            save_presets_state(path, {"X": {"fps": 120}})
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], PRESETS_SCHEMA)
            self.assertEqual(payload["kind"], "cinepulse.presets")
            self.assertTrue(path.with_suffix(".json.bak").is_file())

    def test_corrupt_presets_recover_validated_backup(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.with_suffix(".json.bak").write_text(
                json.dumps({"schema": PRESETS_SCHEMA, "kind": "cinepulse.presets", "items": {"Safe": {"fps": 60}}}),
                encoding="utf-8",
            )
            path.write_text("not-json", encoding="utf-8")
            presets, migrated = load_presets_state(path)
            self.assertTrue(migrated)
            self.assertEqual(presets["Safe"]["fps"], 60)

    def test_future_preset_schema_is_rejected(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.write_text(json.dumps({"schema": 999, "kind": "cinepulse.presets", "items": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_presets_state(path)


if __name__ == "__main__":
    import unittest
    unittest.main()
