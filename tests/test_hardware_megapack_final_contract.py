from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HardwareMegaPackFinalContractTests(unittest.TestCase):
    def text(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8", errors="replace")

    def test_no_temporary_workflow_survives_branch_tree(self) -> None:
        workflows = ROOT / ".github" / "workflows"
        leftovers = [
            path.name for path in workflows.glob("*.yml")
            if path.name.lower().startswith(("_tmp-", "tmp-")) or "temporary" in path.name.lower()
        ]
        self.assertEqual([], leftovers)

    def test_h6_desktop_export_is_evidence_gated_with_cpu_rollback(self) -> None:
        view = self.text("src/cinepulse/ui/composer_view.py")
        dispatcher = self.text("src/cinepulse/composer_auto_export.py")
        compositor = self.text("src/cinepulse/gpu_compositor.py")
        self.assertIn("from ..composer_auto_export import export_composer_auto", view)
        self.assertIn("result = export_composer_auto(", view)
        self.assertNotIn("result = export_composer_reference(", view)
        self.assertIn("evidence_store.invalidate(route.key)", dispatcher)
        self.assertIn("export_composer_reference(", dispatcher)
        self.assertIn("except InterruptedError", dispatcher)
        self.assertIn("COMPOSITOR_MAX_STACK_LAYERS = 4", compositor)
        self.assertIn("overlay_stack_contract_token", compositor)
        self.assertIn("hwdownload,format=yuv420p[vout]", compositor)

    def test_h7_is_external_preview_only_and_rolls_back_to_ncnn(self) -> None:
        contract = self.text("src/cinepulse/tensorrt_preview.py")
        runtime = self.text("src/cinepulse/tensorrt_preview_runtime.py")
        stable_surface = "\n".join(
            self.text(path).lower()
            for path in ("pyproject.toml", "requirements.lock", "requirements-neural.lock", "installer/Start-CinePulse.ps1")
        )
        self.assertNotIn("tensorrt", stable_surface)
        self.assertIn("stable_distribution_allowed", contract)
        self.assertIn("return False", contract)
        self.assertIn("--cinepulse-backend-info", contract)
        self.assertIn("ncnn_baseline_fingerprint", contract)
        self.assertIn("request.store.approved", runtime)
        self.assertIn("request.store.invalidate(key)", runtime)
        self.assertIn("Path(fallback())", runtime)
        self.assertIn("except InterruptedError", runtime)

    def test_h8_never_mutates_global_power_or_realtime_priority(self) -> None:
        h8 = "\n".join(
            self.text(path).lower()
            for path in (
                "src/cinepulse/overnight_runtime.py",
                "src/cinepulse/adaptive_runtime.py",
                "scripts/overnight_acceptance.py",
            )
        )
        forbidden = (
            "realtime_priority_class",
            "setpriorityclass",
            "powercfg",
            "--power-limit",
            "nvidia-settings",
        )
        for token in forbidden:
            self.assertNotIn(token, h8)
        self.assertIn("throughput", h8)
        self.assertIn("temperature_c", h8)
        self.assertIn("power_w", h8)
        self.assertIn("disk_write_mbps", h8)

    def test_preview_acceleration_does_not_enter_stable_render_plan(self) -> None:
        render_plan = self.text("src/cinepulse/render_plan.py")
        for token in (
            "OverlayComposerState",
            "composer_auto_export",
            "gpu_compositor",
            "TensorRt",
            "tensorrt_preview",
        ):
            self.assertNotIn(token, render_plan)


if __name__ == "__main__":
    unittest.main()
