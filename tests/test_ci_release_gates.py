from __future__ import annotations

import unittest
from pathlib import Path

from scripts.ci_gate import CPU_STEPS, GPU_STEPS, MEDIA_STEPS, PROFILES, SOURCE_STEPS

ROOT = Path(__file__).resolve().parents[1]


class CiReleaseGateTests(unittest.TestCase):
    def test_profiles_cover_source_cpu_and_gpu_boundaries(self) -> None:
        self.assertEqual(SOURCE_STEPS, PROFILES["source"])
        self.assertEqual(CPU_STEPS, PROFILES["cpu"])
        self.assertEqual(MEDIA_STEPS, PROFILES["media"])
        self.assertEqual(GPU_STEPS, PROFILES["gpu"])
        names = {step.name for step in CPU_STEPS + MEDIA_STEPS}
        self.assertTrue({
            "smoke-basic", "smoke-audio", "smoke-vfx", "cancel-recovery",
            "delivery-matrix", "hdr", "sdr10-color", "storage",
            "verification", "neural-chunks-contract",
        }.issubset(names))

    def test_every_historical_light_integration_is_in_cpu_profile(self) -> None:
        commands = "\n".join(" ".join(step.command) for step in CPU_STEPS + MEDIA_STEPS)
        for script in (
            "integration_smoke.py", "integration_cancel.py", "integration_delivery.py",
            "integration_hdr.py", "integration_color.py", "integration_storage.py",
            "integration_verification.py", "integration_neural_chunks.py",
        ):
            self.assertIn(script, commands)

    def test_quality_workflow_has_matrix_and_cpu_integration(self) -> None:
        text = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")
        self.assertIn("source-matrix:", text)
        self.assertIn("cpu-integration:", text)
        self.assertIn("media-integration:", text)
        self.assertIn("'3.11'", text)
        self.assertIn("'3.13'", text)
        self.assertIn("--profile cpu", text)
        self.assertIn("--profile media", text)
        self.assertIn("actions/upload-artifact@v7", text)

    def test_release_candidate_builds_and_tests_both_distribution_modes(self) -> None:
        text = (ROOT / ".github/workflows/release-candidate.yml").read_text(encoding="utf-8")
        for needle in (
            "--profile release-light", "Build-Portable.ps1", "Test-Updater.ps1",
            "Build-Msi.ps1", "Test-Msi.ps1", "Test-MsiLifecycle.ps1", "windows-latest",
        ):
            self.assertIn(needle, text)

    def test_gpu_workflow_is_guarded_and_self_hosted(self) -> None:
        text = (ROOT / ".github/workflows/gpu-acceptance.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("pull_request:", text)
        self.assertIn("self-hosted", text)
        self.assertIn("cinepulse-gpu", text)
        self.assertIn("--profile gpu", text)
        self.assertIn("github.event.pull_request.head.repo.full_name == github.repository", text)
        self.assertIn("github.actor == 'Faysk'", text)
        self.assertIn("Recovery RIFE 8K UHD acceptance", text)

    def test_release_gate_documents_phase9_contract(self) -> None:
        text = (ROOT / "scripts/release_gate.py").read_text(encoding="utf-8")
        self.assertIn("CORE_INTEGRITY_PHASE9_CI_RELEASE_GATES.md", text)
        self.assertIn("release-candidate.yml", text)
        self.assertIn("gpu-acceptance.yml", text)

    def test_msi_lifecycle_gate_is_ci_guarded_and_suppresses_bootstrap(self) -> None:
        script = (ROOT / "scripts/Test-MsiLifecycle.ps1").read_text(encoding="utf-8-sig")
        wix = (ROOT / "installer/wix/Product.wxs").read_text(encoding="utf-8-sig")
        self.assertIn("CINEPULSE_CI_ALLOW_MSI_LIFECYCLE", script)
        self.assertIn("CINEPULSE_SKIP_BOOTSTRAP=1", script)
        self.assertIn("CINEPULSE_SKIP_BOOTSTRAP", wix)

    def test_ci_steps_have_bounded_timeouts(self) -> None:
        for profile, steps in PROFILES.items():
            for step in steps:
                self.assertGreater(step.timeout_seconds, 0, f"{profile}/{step.name}")
        self.assertGreaterEqual(min(step.timeout_seconds for step in GPU_STEPS), 900)

    def test_cancellable_subprocesses_are_isolated_on_posix(self) -> None:
        text = (ROOT / "src/cinepulse/studio.py").read_text(encoding="utf-8")
        self.assertIn("from .process_control import popen_group_kwargs, terminate_process_tree", text)
        self.assertGreaterEqual(text.count("**popen_group_kwargs()"), 4)


if __name__ == "__main__":
    unittest.main()
