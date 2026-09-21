from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cinepulse.state_store import (
    PRESETS_SCHEMA,
    QUEUE_SCHEMA,
    StateSchemaTooNew,
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

    def test_future_queue_primary_cannot_be_overwritten_by_save(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            original = json.dumps({"schema": 999, "kind": "cinepulse.queue.v2", "items": [{"id": 99}]})
            path.write_text(original, encoding="utf-8")

            with self.assertRaises(StateSchemaTooNew):
                save_queue_state(path, [{"id": 1}])

            self.assertEqual(original, path.read_text(encoding="utf-8"))
            self.assertFalse(path.with_suffix(".json.bak").exists())

    def test_future_queue_backup_also_blocks_older_save(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            backup = path.with_suffix(".json.bak")
            path.write_text(
                json.dumps({"schema": QUEUE_SCHEMA, "kind": "cinepulse.queue", "items": [{"id": 1}]}),
                encoding="utf-8",
            )
            future = json.dumps({"schema": 999, "kind": "cinepulse.queue.v2", "items": [{"id": 99}]})
            backup.write_text(future, encoding="utf-8")
            before_primary = path.read_bytes()
            before_backup = backup.read_bytes()

            with self.assertRaises(StateSchemaTooNew):
                save_queue_state(path, [{"id": 2}])

            self.assertEqual(before_primary, path.read_bytes())
            self.assertEqual(before_backup, backup.read_bytes())

    def test_legacy_presets_dict_is_migratable(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.write_text(json.dumps({"Meu preset": {"fps": 60}}), encoding="utf-8")
            presets, migrated = load_presets_state(path)
            self.assertTrue(migrated)
            self.assertEqual(presets["Meu preset"]["fps"], 60)

    def test_legacy_preset_named_schema_is_not_mistaken_for_version_envelope(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.write_text(
                json.dumps({"schema": {"fps": 60}, "Outro": {"fps": 120}}),
                encoding="utf-8",
            )
            presets, migrated = load_presets_state(path)
            self.assertTrue(migrated)
            self.assertEqual({"fps": 60}, presets["schema"])
            self.assertEqual(120, presets["Outro"]["fps"])

    def test_presets_save_is_versioned_and_backed_up(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.write_text("{}", encoding="utf-8")
            save_presets_state(path, {"X": {"fps": 120}})
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], PRESETS_SCHEMA)
            self.assertEqual(payload["kind"], "cinepulse.presets")
            self.assertTrue(path.with_suffix(".json.bak").is_file())

    def test_future_presets_primary_cannot_be_overwritten_by_save(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            original = json.dumps({"schema": 999, "kind": "cinepulse.presets.v2", "items": {"Future": {"fps": 240}}})
            path.write_text(original, encoding="utf-8")

            with self.assertRaises(StateSchemaTooNew):
                save_presets_state(path, {"Old": {"fps": 60}})

            self.assertEqual(original, path.read_text(encoding="utf-8"))
            self.assertFalse(path.with_suffix(".json.bak").exists())

    def test_future_presets_backup_also_blocks_older_save(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            backup = path.with_suffix(".json.bak")
            path.write_text(
                json.dumps({"schema": PRESETS_SCHEMA, "kind": "cinepulse.presets", "items": {"Current": {"fps": 60}}}),
                encoding="utf-8",
            )
            future = json.dumps({"schema": 999, "kind": "cinepulse.presets.v2", "items": {"Future": {"fps": 240}}})
            backup.write_text(future, encoding="utf-8")
            before_primary = path.read_bytes()
            before_backup = backup.read_bytes()

            with self.assertRaises(StateSchemaTooNew):
                save_presets_state(path, {"Old": {"fps": 30}})

            self.assertEqual(before_primary, path.read_bytes())
            self.assertEqual(before_backup, backup.read_bytes())

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
