from __future__ import annotations

import io
import json
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
    _handoff_script,
    _read_limited,
    _safe_extract,
    _validated_update_info,
    check_github_release,
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


def _release_payload(version: str = "1.2.0", *, digest: bool = True) -> bytes:
    assets = []
    for name, marker in (
        (f"CinePulse-{version}-windows-portable.zip", "a"),
        (f"CinePulse-{version}-Setup.msi", "b"),
    ):
        asset = {
            "name": name,
            "state": "uploaded",
            "browser_download_url": f"https://github.com/Faysk/CinePulse/releases/download/v{version}/{name}",
        }
        if digest:
            asset["digest"] = "sha256:" + marker * 64
        assets.append(asset)
    assets.append(
        {
            "name": "SHA256SUMS.txt",
            "state": "uploaded",
            "browser_download_url": f"https://github.com/Faysk/CinePulse/releases/download/v{version}/SHA256SUMS.txt",
            "digest": "sha256:" + "c" * 64,
        }
    )
    return json.dumps(
        {
            "tag_name": f"v{version}",
            "html_url": f"https://github.com/Faysk/CinePulse/releases/tag/v{version}",
            "draft": False,
            "prerelease": False,
            "assets": assets,
        }
    ).encode("utf-8")


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

    def test_release_discovery_uses_asset_digest_without_second_request(self) -> None:
        response = _Response(_release_payload())
        with patch("cinepulse.update_manager.urllib.request.urlopen", return_value=response) as open_url:
            info = check_github_release("1.1.3", installation="portable", timeout=3)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual("1.2.0", info.version)
        self.assertEqual("portable", info.package_kind)
        self.assertEqual("a" * 64, info.sha256)
        self.assertEqual("CinePulse-1.2.0-windows-portable.zip", info.asset_name)
        self.assertEqual(1, open_url.call_count)

    def test_release_discovery_selects_msi_for_installed_mode(self) -> None:
        response = _Response(_release_payload())
        with patch("cinepulse.update_manager.urllib.request.urlopen", return_value=response):
            info = check_github_release("1.1.3", installation="installed", timeout=3)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual("msi", info.package_kind)
        self.assertEqual("b" * 64, info.sha256)
        self.assertTrue(info.download_url.endswith("CinePulse-1.2.0-Setup.msi"))

    def test_current_release_does_not_offer_update(self) -> None:
        response = _Response(_release_payload("1.1.3"))
        with patch("cinepulse.update_manager.urllib.request.urlopen", return_value=response):
            self.assertIsNone(check_github_release("1.1.3", installation="portable", timeout=3))

    def test_release_without_digest_falls_back_to_sha256sums(self) -> None:
        release = _Response(_release_payload(digest=False))
        sums = _Response(
            (
                ("d" * 64) + "  CinePulse-1.2.0-windows-portable.zip\n" +
                ("e" * 64) + "  CinePulse-1.2.0-Setup.msi\n"
            ).encode("ascii")
        )
        with patch("cinepulse.update_manager.urllib.request.urlopen", side_effect=[release, sums]) as open_url:
            info = check_github_release("1.1.3", installation="portable", timeout=3)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual("d" * 64, info.sha256)
        self.assertEqual(2, open_url.call_count)

    def test_release_asset_url_must_stay_on_expected_github_release(self) -> None:
        payload = json.loads(_release_payload().decode("utf-8"))
        payload["assets"][0]["browser_download_url"] = "https://example.invalid/CinePulse-1.2.0-windows-portable.zip"
        with patch(
            "cinepulse.update_manager.urllib.request.urlopen",
            return_value=_Response(json.dumps(payload).encode("utf-8")),
        ):
            with self.assertRaises(ValueError):
                check_github_release("1.1.3", installation="portable", timeout=3)

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

    def test_staging_rejects_unknown_package_kind(self) -> None:
        with self.assertRaises(ValueError):
            _validated_update_info(
                UpdateInfo("1.1.1", "https://example.invalid/CinePulse.zip", "a" * 64, package_kind="exe")
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

    def test_msi_handoff_waits_for_app_before_major_upgrade_and_reopens(self) -> None:
        info = UpdateInfo(
            "1.2.0",
            "https://github.com/Faysk/CinePulse/releases/download/v1.2.0/CinePulse-1.2.0-Setup.msi",
            "b" * 64,
            package_kind="msi",
            asset_name="CinePulse-1.2.0-Setup.msi",
        )
        script = _handoff_script(info, Path(r"C:\Temp\update.msi"), Path(r"C:\Apps\CinePulse"), 4321)
        self.assertIn("Wait-Process -Id $PidToWait", script)
        self.assertIn("msiexec.exe", script)
        self.assertIn("/passive /norestart", script)
        self.assertIn("CinePulse-Installed.cmd", script)
        self.assertLess(script.index("Wait-Process"), script.index("msiexec.exe"))

    def test_portable_handoff_waits_then_relaunches_existing_transaction(self) -> None:
        info = UpdateInfo(
            "1.2.0",
            "https://github.com/Faysk/CinePulse/releases/download/v1.2.0/CinePulse-1.2.0-windows-portable.zip",
            "a" * 64,
            package_kind="portable",
        )
        script = _handoff_script(info, Path(r"C:\App\.runtime\pending-update.json"), Path(r"C:\App"), 123)
        self.assertIn("pending-update.json", script)
        self.assertIn("CinePulse.cmd", script)
        self.assertNotIn("msiexec.exe", script)
        self.assertLess(script.index("Wait-Process"), script.index("Start-Process"))

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
