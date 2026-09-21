from __future__ import annotations

import json
import shutil
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cinepulse import experimental_components


class ExperimentalComponentTests(unittest.TestCase):
    def _archive(self, root: Path) -> Path:
        archive = root / "fixture.zip"
        payload = root / "payload"
        bundle = payload / "bundle"
        bundle.mkdir(parents=True)
        (bundle / "new.bin").write_bytes(b"new")
        with zipfile.ZipFile(archive, "w") as output:
            output.write(bundle / "new.bin", "bundle/new.bin")
        return archive

    def _download_from(self, archive: Path):
        def download(_url: str, destination: Path, _expected_hash: str, _log) -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, destination)
        return download

    def test_stale_marker_does_not_hide_new_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            components = root / "components"
            destination = components / "ai" / "preview"
            destination.mkdir(parents=True)
            (destination / "old.bin").write_bytes(b"old")
            (destination / ".cinepulse-experimental.json").write_text(
                json.dumps({"schema": 1, "sha256": "old-hash"}),
                encoding="utf-8",
            )
            archive = self._archive(root)
            entry = {"destination": "preview", "url": "https://example.invalid/x.zip", "sha256": "new-hash"}

            with (
                patch.object(experimental_components, "PATHS", SimpleNamespace(components=components)),
                patch.object(experimental_components, "_download", side_effect=self._download_from(archive)),
            ):
                experimental_components._install_archive(entry, lambda _message: None)

            self.assertTrue((destination / "new.bin").is_file())
            self.assertFalse((destination / "old.bin").exists())
            marker = json.loads((destination / ".cinepulse-experimental.json").read_text(encoding="utf-8"))
            self.assertEqual(2, marker["schema"])
            self.assertEqual("new-hash", marker["sha256"])
            self.assertTrue(marker["tree_fingerprint"].startswith("tree-v1:"))
            self.assertTrue(
                experimental_components._marker_matches(
                    destination / ".cinepulse-experimental.json",
                    "new-hash",
                )
            )
            self.assertFalse(destination.with_name("preview.previous").exists())

    def test_marker_failure_restores_previous_component(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            components = root / "components"
            destination = components / "ai" / "preview"
            destination.mkdir(parents=True)
            (destination / "old.bin").write_bytes(b"old")
            archive = self._archive(root)
            entry = {"destination": "preview", "url": "https://example.invalid/x.zip", "sha256": "new-hash"}

            with (
                patch.object(experimental_components, "PATHS", SimpleNamespace(components=components)),
                patch.object(experimental_components, "_download", side_effect=self._download_from(archive)),
                patch.object(experimental_components, "_atomic_json", side_effect=OSError("disk full")),
            ):
                with self.assertRaisesRegex(OSError, "disk full"):
                    experimental_components._install_archive(entry, lambda _message: None)

            self.assertTrue((destination / "old.bin").is_file())
            self.assertFalse((destination / "new.bin").exists())
            self.assertFalse(destination.with_name("preview.previous").exists())

    def test_invalid_marker_is_not_considered_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / ".cinepulse-experimental.json"
            marker.write_text("{broken", encoding="utf-8")
            self.assertFalse(experimental_components._marker_matches(marker, "hash"))


    def test_marker_detects_modified_or_missing_installed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "bundle"
            destination.mkdir()
            payload = destination / "model.py"
            payload.write_bytes(b"original")
            marker = destination / ".cinepulse-experimental.json"
            marker.write_text(
                json.dumps(
                    {
                        "schema": 2,
                        "sha256": "archive-hash",
                        "tree_fingerprint": experimental_components._tree_fingerprint(destination),
                    }
                ),
                encoding="utf-8",
            )

            self.assertTrue(experimental_components._marker_matches(marker, "archive-hash"))

            payload.write_bytes(b"tampered")
            self.assertFalse(experimental_components._marker_matches(marker, "archive-hash"))

            marker.write_text(
                json.dumps(
                    {
                        "schema": 2,
                        "sha256": "archive-hash",
                        "tree_fingerprint": experimental_components._tree_fingerprint(destination),
                    }
                ),
                encoding="utf-8",
            )
            payload.unlink()
            self.assertFalse(experimental_components._marker_matches(marker, "archive-hash"))

    def test_legacy_marker_without_tree_fingerprint_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "bundle"
            destination.mkdir()
            (destination / "model.py").write_bytes(b"model")
            marker = destination / ".cinepulse-experimental.json"
            marker.write_text(
                json.dumps({"schema": 1, "sha256": "archive-hash"}),
                encoding="utf-8",
            )
            self.assertFalse(experimental_components._marker_matches(marker, "archive-hash"))

    def test_archive_rejects_symlink_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "payload.zip"
            destination = root / "out"
            info = zipfile.ZipInfo("bundle/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(info, "../../outside")
            with self.assertRaisesRegex(RuntimeError, "link simbólico"):
                experimental_components._safe_extract_archive(archive, destination)
            self.assertFalse((root / "outside").exists())

    def test_archive_rejects_case_insensitive_duplicate_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "payload.zip"
            destination = root / "out"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("bundle/Foo.py", b"one")
                bundle.writestr("bundle/foo.py", b"two")
            with self.assertRaisesRegex(RuntimeError, "entrada duplicada"):
                experimental_components._safe_extract_archive(archive, destination)

    def test_archive_rejects_windows_style_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "payload.zip"
            destination = root / "out"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(r"bundle\..\..\outside.txt", b"escape")
            with self.assertRaisesRegex(RuntimeError, "caminho inseguro"):
                experimental_components._safe_extract_archive(archive, destination)
            self.assertFalse((root / "outside.txt").exists())

    def test_archive_rejects_expanded_size_over_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "payload.zip"
            destination = root / "out"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("bundle/file.bin", b"1234")
            with patch.object(experimental_components, "MAX_ARCHIVE_EXTRACTED_BYTES", 3):
                with self.assertRaisesRegex(RuntimeError, "expandido excede"):
                    experimental_components._safe_extract_archive(archive, destination)



if __name__ == "__main__":
    unittest.main()
