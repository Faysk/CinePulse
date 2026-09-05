from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DistributionPhase8Tests(unittest.TestCase):
    def test_runtime_lock_has_hash(self) -> None:
        lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")
        self.assertIn("numpy==2.5.2", lock)
        self.assertIn("--python-version 3.14.7", lock)
        self.assertIn("--python-platform x86_64-pc-windows-msvc", lock)
        self.assertIn("--hash=sha256:", lock)

    def test_bootstrap_forces_managed_python(self) -> None:
        text = (ROOT / "installer" / "Start-CinePulse.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("--python-preference only-managed", text)
        self.assertNotIn("Find-SystemPython", text)
        self.assertIn("CINEPULSE_COMPONENTS_DIR", text)
        self.assertNotIn("$UserDataRoot", text)
        self.assertIn("$RuntimeRoot = Join-Path $ProjectRoot '.runtime'", text)
        self.assertIn("$DataRoot = Join-Path $ProjectRoot 'data'", text)
        self.assertIn("$CacheRoot = Join-Path $ProjectRoot 'cache'", text)
        self.assertIn("$TempRoot = Join-Path $ProjectRoot 'temp'", text)
        self.assertIn("PYTHONNOUSERSITE", text)

    def test_msi_has_separate_launcher_and_dynamic_version(self) -> None:
        wix = (ROOT / "installer" / "wix" / "Product.wxs").read_text(encoding="utf-8-sig")
        self.assertIn("$(var.ProductVersion)", wix)
        self.assertIn("CinePulse-Installed.cmd", wix)
        self.assertIn("Install-CinePulse-Installed.cmd", wix)
        self.assertIn("CinePulseIcon", wix)
        self.assertNotIn('Target="[INSTALLFOLDER]CinePulse.cmd"', wix)

    def test_installed_launchers_force_nonportable(self) -> None:
        launcher = (ROOT / "CinePulse-Installed.cmd").read_text(encoding="utf-8")
        installer = (ROOT / "Install-CinePulse-Installed.cmd").read_text(encoding="utf-8")
        self.assertIn("-NonPortable", launcher)
        self.assertIn("-NonPortable -InstallOnly", installer)

    def test_windows_icon_is_real_ico(self) -> None:
        icon = ROOT / "assets" / "cinepulse.ico"
        self.assertGreater(icon.stat().st_size, 1024)
        self.assertEqual(icon.read_bytes()[:4], b"\x00\x00\x01\x00")

    def test_sbom_script_returns_cyclonedx(self) -> None:
        from scripts.generate_sbom import build_sbom

        payload = build_sbom()
        self.assertEqual(payload["bomFormat"], "CycloneDX")
        self.assertRegex(payload["serialNumber"], r"^urn:uuid:[0-9a-f-]{36}$")
        names = {item["name"] for item in payload["components"]}
        self.assertTrue(
            {"numpy", "Python", "FFmpeg", "Real-ESRGAN", "RIFE", "Demucs", "PyTorch", "SoundFile"}.issubset(names)
        )
        self.assertNotIn("torchaudio", names)
        numpy = next(item for item in payload["components"] if item["name"] == "numpy")
        self.assertEqual(len(numpy.get("hashes", [])), 1)
        properties = {item["name"]: item["value"] for item in payload["metadata"]["properties"]}
        self.assertEqual(properties["cinepulse:transitive-demucs-lock"], "hash-locked-windows-python-3.14")
        self.assertEqual(properties["cinepulse:cuda-policy"], "local-pytorch-runtime-no-global-toolkit")

    def test_build_msi_has_signing_hook(self) -> None:
        build = (ROOT / "scripts" / "Build-Msi.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("ConvertTo-MsiVersion", build)
        self.assertIn("CertificateThumbprint", build)
        self.assertIn("AuthenticodeSigned", build)
        self.assertIn("ProductVersion=$MsiVersion", build)

    def test_installed_ui_component_repairs_preserve_nonportable_mode(self) -> None:
        studio = (ROOT / "src" / "cinepulse" / "studio.py").read_text(encoding="utf-8")
        # Two component launch/repair paths must preserve installed mode.
        # The legacy updater used to contribute a third unrelated text match;
        # the one-click updater now snapshots installation mode once.
        self.assertGreaterEqual(studio.count('installation_mode(APP_DIR) == "installed"'), 2)
        self.assertGreaterEqual(studio.count('command.append("-NonPortable")'), 2)
        self.assertIn("install_mode = installation_mode(APP_DIR)", studio)
        self.assertIn("installation=install_mode", studio)

    def test_windows_mutex_uses_pointer_sized_handle_and_closes_duplicates(self) -> None:
        runtime = (ROOT / "src" / "cinepulse" / "runtime_distribution.py").read_text(encoding="utf-8")
        self.assertIn("CreateMutexW(None, True", runtime)
        self.assertIn("CreateMutexW.restype = wintypes.HANDLE", runtime)
        self.assertIn("ReleaseMutex.argtypes = [wintypes.HANDLE]", runtime)
        self.assertIn("CloseHandle.argtypes = [wintypes.HANDLE]", runtime)
        self.assertIn("kernel32.CloseHandle(handle)", runtime)
        self.assertIn("ctypes.get_last_error() == 183", runtime)


if __name__ == "__main__":
    unittest.main()
