from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cinepulse.integrity import MANIFEST_NAME, sha256, verify


class IntegrityTests(unittest.TestCase):
    def test_verifies_and_detects_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "hello.txt"
            source.write_text("ok", encoding="utf-8")
            (root / MANIFEST_NAME).write_text(
                json.dumps({"schema": 1, "files": {"hello.txt": sha256(source)}}), encoding="utf-8"
            )
            self.assertTrue(verify(root)["ok"])
            source.write_text("changed", encoding="utf-8")
            result = verify(root)
            self.assertFalse(result["ok"])
            self.assertEqual(result["changed"], ["hello.txt"])


if __name__ == "__main__":
    unittest.main()
