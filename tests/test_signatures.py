from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.signatures import verify_file
from cinepulse import update_manager


class SignatureTests(unittest.TestCase):
    @patch("cinepulse.signatures.subprocess.run")
    def test_minisign_verify_command(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="ok")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            message = root / "manifest.json"; message.write_text("{}", encoding="utf-8")
            signature = root / "manifest.minisig"; signature.write_text("sig", encoding="utf-8")
            verify_file(message, signature, "RWTEST", executable="minisign.exe")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "minisign.exe")
        self.assertIn("-Vm", command)
        self.assertIn("-P", command)
        self.assertIn("RWTEST", command)

    @patch("cinepulse.signatures.subprocess.run")
    def test_invalid_signature_is_fatal(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, stdout="bad signature")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            message = root / "manifest.json"; message.write_text("{}", encoding="utf-8")
            signature = root / "manifest.minisig"; signature.write_text("sig", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                verify_file(message, signature, "RWTEST", executable="minisign.exe")

    @patch("cinepulse.update_manager.verify_bytes")
    @patch("cinepulse.update_manager.urllib.request.urlopen")
    @patch("cinepulse.update_manager.configured_channel")
    def test_signed_update_verifies_raw_manifest_before_trust(self, channel, urlopen, verify_bytes_mock) -> None:
        feed = "https://example.invalid/cinepulse-update.json"
        signature_url = feed + ".minisig"
        manifest = json.dumps({
            "schema": 1, "version": "9.0.0",
            "download_url": "https://example.invalid/CinePulse.zip",
            "sha256": "a" * 64,
        }).encode("utf-8")
        signature = b"trusted-signature"
        channel.return_value = update_manager.UpdateChannel(feed, True, "RWTEST", signature_url)
        urlopen.side_effect = [io.BytesIO(manifest), io.BytesIO(signature)]
        info = update_manager.check(feed, "1.0.0")
        verify_bytes_mock.assert_called_once_with(manifest, signature, "RWTEST")
        self.assertEqual(info.version, "9.0.0")

    @patch("cinepulse.update_manager.verify_bytes", side_effect=RuntimeError("assinatura inválida"))
    @patch("cinepulse.update_manager.urllib.request.urlopen")
    @patch("cinepulse.update_manager.configured_channel")
    def test_invalid_signed_update_is_fatal_before_manifest_use(self, channel, urlopen, _verify) -> None:
        feed = "https://example.invalid/cinepulse-update.json"
        manifest = b'{"schema":1,"version":"9.0.0","download_url":"https://example.invalid/x.zip","sha256":"' + (b'a' * 64) + b'"}'
        channel.return_value = update_manager.UpdateChannel(feed, True, "RWTEST", feed + ".minisig")
        urlopen.side_effect = [io.BytesIO(manifest), io.BytesIO(b"bad")]
        with self.assertRaisesRegex(RuntimeError, "assinatura inválida"):
            update_manager.check(feed, "1.0.0")


if __name__ == "__main__":
    unittest.main()
