from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "installer" / "Start-CinePulse.ps1"
APPLIER = ROOT / "installer" / "Apply-CinePulseUpdate.ps1"
UPDATER_TEST = ROOT / "scripts" / "Test-Updater.ps1"


class BootstrapHardeningTests(unittest.TestCase):
    def test_portable_update_is_delegated_to_transactional_applier(self) -> None:
        start = START.read_text(encoding="utf-8-sig")
        self.assertIn("Apply-CinePulseUpdate.ps1", start)
        self.assertIn("-ProjectRoot $ProjectRoot -RuntimeRoot $RuntimeRoot", start)
        self.assertNotIn("$RootFiles = @(", start)
        self.assertTrue(APPLIER.is_file())

    def test_update_preserves_mutable_roots_and_validates_package_twice(self) -> None:
        text = APPLIER.read_text(encoding="utf-8-sig")
        for root in (".runtime", "components", "data", "cache", "temp"):
            self.assertIn(f"'{root}'", text)
        self.assertGreaterEqual(text.count("Test-PackageManifest -PackageRoot"), 2)
        self.assertIn("Get-FileHash -Algorithm SHA256", text)
        self.assertIn("CINEPULSE_CI_UPDATE_FAIL_AFTER_REMOVE", text)
        self.assertIn("CINEPULSE_CI_UPDATE_FAIL_AFTER_COPY", text)
        self.assertIn("CINEPULSE_UPDATE_ROLLBACK_OK", text)

    def test_updater_acceptance_exercises_partial_copy_rollback_and_retry(self) -> None:
        text = UPDATER_TEST.read_text(encoding="utf-8-sig")
        self.assertIn("CINEPULSE_CI_UPDATE_FAIL_AFTER_COPY", text)
        self.assertIn("CINEPULSE_UPDATE_ROLLBACK_FAULT_OK", text)
        self.assertIn("future-root-file.txt", text)
        self.assertIn("preserve-me.txt", text)
        self.assertIn("CINEPULSE_UPDATE_APPLY_SMOKE_OK", text)

    def test_uv_and_ffmpeg_cache_are_manifest_identity_aware(self) -> None:
        text = START.read_text(encoding="utf-8-sig")
        self.assertIn("uv-version.txt", text)
        self.assertIn("$ExpectedVersion = [string]$BootstrapManifest.uv.version", text)
        self.assertIn("Install-VerifiedArchive -Key 'ffmpeg'", text)
        self.assertNotIn("if ((Test-Path -LiteralPath $FfmpegExe) -and (Test-Path -LiteralPath $FfprobeExe)) { return }", text)

    def test_components_require_version_hash_and_atomic_promotion(self) -> None:
        text = START.read_text(encoding="utf-8-sig")
        self.assertIn("$StateHash = ([string]$State.sha256).ToLowerInvariant()", text)
        self.assertIn("$ManifestHash = ([string]$Manifest.sha256).ToLowerInvariant()", text)
        self.assertIn("$State.version -eq $Manifest.version -and $StateHash -eq $ManifestHash", text)
        self.assertIn("CINEPULSE_CI_COMPONENT_FAIL_AFTER_PROMOTE", text)
        self.assertIn("if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }", text)
        self.assertIn("if (Test-Path -LiteralPath $Previous) { Move-Item -LiteralPath $Previous -Destination $Destination }", text)

    def test_python_runtime_self_heals_when_manifest_version_changes(self) -> None:
        text = START.read_text(encoding="utf-8-sig")
        self.assertIn("$ExpectedPythonVersion = [string]$BootstrapManifest.python.version", text)
        self.assertIn("$RebuildRuntime = $Repair -or -not (Test-Path -LiteralPath $PythonExe)", text)
        self.assertIn("Runtime Python mudou:", text)
        self.assertIn("--python $ExpectedPythonVersion --python-preference only-managed", text)
        self.assertIn('$ExpectedState = "$ExpectedPythonVersion`n$ProjectHash`n$LockHash"', text)

    def test_demucs_ready_state_binds_full_runtime_identity(self) -> None:
        text = START.read_text(encoding="utf-8-sig")
        for marker in (
            "$State.python -eq $BootstrapManifest.python.version",
            "$State.demucs -eq $BootstrapManifest.demucs.version",
            "$State.torch -eq $BootstrapManifest.demucs.torch_version",
            "$State.soundfile -eq $BootstrapManifest.demucs.soundfile_version",
            "$State.cuda_runtime -eq $BootstrapManifest.demucs.cuda_runtime",
            "$State.torch_index -eq $BootstrapManifest.demucs.torch_index",
        ):
            self.assertIn(marker, text)
        self.assertIn("importlib.metadata as m, platform, torch", text)

    def test_no_temporary_audit_writer_or_patch_helpers_ship(self) -> None:
        self.assertFalse((ROOT / ".github" / "workflows" / "audit-updater-patch.yml").exists())
        self.assertFalse((ROOT / "scripts" / "_audit_patch_updater.py").exists())
        self.assertFalse((ROOT / "scripts" / "_audit_bootstrap_patch_v2.py").exists())


if __name__ == "__main__":
    unittest.main()
