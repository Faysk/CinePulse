from __future__ import annotations

import json
import shutil
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
            self.assertEqual("new-hash", marker["sha256"])
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


if __name__ == "__main__":
    unittest.main()
