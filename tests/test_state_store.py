from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from cinepulse.state_store import (
    PRESETS_SCHEMA, QUEUE_SCHEMA, load_presets_state, load_queue_state,
    save_presets_state, save_queue_state,
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

    def test_future_queue_schema_is_rejected(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "queue.json"
            path.write_text(json.dumps({"schema": 999, "kind": "cinepulse.queue", "items": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_queue_state(path)

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

    def test_future_preset_schema_is_rejected(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "presets.json"
            path.write_text(json.dumps({"schema": 999, "kind": "cinepulse.presets", "items": {}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_presets_state(path)


if __name__ == "__main__":
    import unittest
    unittest.main()
