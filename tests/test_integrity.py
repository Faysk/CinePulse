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


    def test_verifies_portable_list_manifest_with_size(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "hello.txt"
            source.write_text("ok", encoding="utf-8")
            manifest = {
                "schema": 1,
                "version": "1.2.19",
                "files": [{
                    "path": "hello.txt",
                    "sha256": sha256(source),
                    "size": source.stat().st_size,
                }],
            }
            (root / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
            result = verify(root)
            self.assertTrue(result["ok"])
            self.assertEqual(1, result["checked"])

            source.write_text("changed", encoding="utf-8")
            result = verify(root)
            self.assertFalse(result["ok"])
            self.assertEqual(["hello.txt"], result["changed"])

    def test_portable_list_manifest_rejects_duplicate_casefolded_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "hello.txt"
            source.write_text("ok", encoding="utf-8")
            digest = sha256(source)
            (root / MANIFEST_NAME).write_text(
                json.dumps({
                    "schema": 1,
                    "files": [
                        {"path": "hello.txt", "sha256": digest, "size": 2},
                        {"path": "HELLO.txt", "sha256": digest, "size": 2},
                    ],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicado"):
                verify(root)

    def test_portable_list_manifest_rejects_unsafe_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / "outside-cinepulse-integrity.txt"
            outside.write_text("nope", encoding="utf-8")
            try:
                (root / MANIFEST_NAME).write_text(
                    json.dumps({
                        "schema": 1,
                        "files": [{
                            "path": "../outside-cinepulse-integrity.txt",
                            "sha256": sha256(outside),
                            "size": outside.stat().st_size,
                        }],
                    }),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, "Caminho inseguro"):
                    verify(root)
            finally:
                outside.unlink(missing_ok=True)


    def test_portable_list_manifest_rejects_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "hello.txt"
            source.write_text("ok", encoding="utf-8")
            absolute = source.resolve().as_posix()
            (root / MANIFEST_NAME).write_text(
                json.dumps({
                    "schema": 1,
                    "files": [{
                        "path": absolute,
                        "sha256": sha256(source),
                        "size": source.stat().st_size,
                    }],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Caminho inseguro"):
                verify(root)


if __name__ == "__main__":
    unittest.main()
