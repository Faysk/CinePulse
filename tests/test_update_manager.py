from __future__ import annotations

import io
import stat
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

from cinepulse.update_manager import (
    UpdateInfo,
    _download_limited,
    _read_limited,
    _safe_extract,
    _validated_update_info,
    is_newer,
    stage,
)


class _Response(io.BytesIO):
    def __init__(self, data: bytes, content_length: str | None = None) -> None:
        super().__init__(data)
        self.headers = {} if content_length is None else {"Content-Length": content_length}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


class UpdateManagerTests(unittest.TestCase):
    def test_release_order(self) -> None:
        self.assertTrue(is_newer("1.0.0", "1.0.0-rc1"))
        self.assertTrue(is_newer("1.0.0-rc2", "1.0.0-beta4"))
        self.assertTrue(is_newer("0.9.0", "0.1.0-alpha.2"))
        self.assertFalse(is_newer("1.2.0", "1.2.0"))
        self.assertFalse(is_newer("1.1.9", "1.2.0"))

    def test_staging_boundary_accepts_normalized_valid_info(self) -> None:
        version, digest = _validated_update_info(
            UpdateInfo(" 1.1.1 ", "https://example.invalid/CinePulse.zip", "A" * 64)
        )
        self.assertEqual(version, "1.1.1")
        self.assertEqual(digest, "a" * 64)

    def test_stage_rejects_invalid_version_before_filesystem_or_network(self) -> None:
        with self.assertRaises(ValueError):
            stage(UpdateInfo("../1.1.1", "https://example.invalid/CinePulse.zip", "a" * 64))

    def test_stage_rejects_non_https_download_before_filesystem_or_network(self) -> None:
        with self.assertRaises(ValueError):
            stage(UpdateInfo("1.1.1", "http://example.invalid/CinePulse.zip", "a" * 64))

    def test_stage_rejects_invalid_sha_before_filesystem_or_network(self) -> None:
        with self.assertRaises(ValueError):
            stage(UpdateInfo("1.1.1", "https://example.invalid/CinePulse.zip", "not-a-sha"))

    def test_staging_rejects_non_https_notes_url(self) -> None:
        with self.assertRaises(ValueError):
            _validated_update_info(
                UpdateInfo("1.1.1", "https://example.invalid/CinePulse.zip", "a" * 64, "http://example.invalid/notes")
            )

    def test_manifest_reader_rejects_oversized_response(self) -> None:
        with self.assertRaises(ValueError):
            _read_limited(io.BytesIO(b"12345"), 4, "manifest")

    def test_download_rejects_declared_oversized_archive_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "update.zip"
            response = _Response(b"small", content_length="100")
            with patch("cinepulse.update_manager.urllib.request.urlopen", return_value=response):
                with self.assertRaises(ValueError):
                    _download_limited(urllib.request.Request("https://example.invalid/update.zip"), destination, 10)

    def test_download_rejects_stream_that_crosses_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "update.zip"
            response = _Response(b"123456")
            with patch("cinepulse.update_manager.urllib.request.urlopen", return_value=response):
                with self.assertRaises(ValueError):
                    _download_limited(urllib.request.Request("https://example.invalid/update.zip"), destination, 5)

    def test_zip_rejects_expanded_size_over_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "payload.zip"
            destination = root / "out"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("CinePulse/CinePulse.cmd", b"1234")
            with patch("cinepulse.update_manager.MAX_UPDATE_EXTRACTED_BYTES", 3):
                with self.assertRaises(ValueError):
                    _safe_extract(archive, destination)

    def test_zip_rejects_symlink_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "payload.zip"
            destination = root / "out"
            destination.mkdir()
            info = zipfile.ZipInfo("CinePulse/link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(info, "../../outside")
            with self.assertRaises(ValueError):
                _safe_extract(archive, destination)

    def test_zip_rejects_case_insensitive_duplicate_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "payload.zip"
            destination = root / "out"
            destination.mkdir()
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("CinePulse/File.txt", b"one")
                bundle.writestr("cinepulse/file.txt", b"two")
            with self.assertRaises(ValueError):
                _safe_extract(archive, destination)


if __name__ == "__main__":
    unittest.main()
