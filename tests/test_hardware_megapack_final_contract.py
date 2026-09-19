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

    def test_composer_exports_use_current_atomic_output_factory(self) -> None:
        cpu = self.text("src/cinepulse/composer_export.py")
        gpu = self.text("src/cinepulse/composer_auto_export.py")
        for text in (cpu, gpu):
            self.assertIn("AtomicOutput.for_path(", text)
            self.assertIn("atomic.prepare()", text)
            self.assertIn("atomic.commit()", text)
            self.assertIn("atomic.discard()", text)
            self.assertNotIn("with AtomicOutput(", text)

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

    def test_tuned_realesrgan_policy_is_capped_by_live_vram_headroom(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        self.assertIn("tuned_limited_by_headroom", studio)
        self.assertIn("realesrgan_live_process_cap(", studio)
        self.assertIn("tuned_policy.process_jobs > live_process_cap", studio)
        self.assertIn("tuning físico", studio)
        self.assertIn("preservado no cache", studio)
        self.assertIn("tile=max(32, min(256, active_policy.tile))", studio)
        self.assertIn(
            "process_jobs=max(1, min(2, fallback_policy.process_jobs, active_policy.process_jobs))",
            studio,
        )
        self.assertIn(
            "load_jobs=max(1, min(2, fallback_policy.load_jobs, active_policy.load_jobs))",
            studio,
        )
        self.assertIn(
            "save_jobs=max(1, min(2, fallback_policy.save_jobs, active_policy.save_jobs))",
            studio,
        )

    def test_realesrgan_recovery_restores_only_physically_proven_policy(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        self.assertIn("recovery_policy = tuned_policy or fallback_policy", studio)
        self.assertIn("recovery_free_vram = vram_free_mb(recovery_policy.gpu_index)", studio)
        self.assertIn("recovery_policy.process_jobs <= recovery_cap", studio)
        self.assertIn("active_policy = recovery_policy", studio)
        self.assertIn("recovery_policy = fallback_policy", studio)
        self.assertIn("H9 VRAM recovery", studio)

    def test_adaptive_recovery_can_restore_only_the_proven_overlap_baseline(self) -> None:
        runtime = self.text("src/cinepulse/adaptive_runtime.py")
        studio = self.text("src/cinepulse/studio.py")
        self.assertIn("self._recovery_window = max(3, min(12, int(recovery_window)))", runtime)
        self.assertIn("ram_percent <= 82.0", runtime)
        self.assertIn("vram_free >= 1536.0", runtime)
        self.assertIn("self._level = max(requested, self._level - 1)", runtime)
        self.assertIn("baseline_overlap_extract = bool(overlap_extract)", studio)
        self.assertIn("baseline_overlap_pack = bool(overlap_pack)", studio)
        self.assertIn(
            "overlap_extract = baseline_overlap_extract and decision.allow_extract_overlap",
            studio,
        )
        self.assertIn(
            "overlap_pack = baseline_overlap_pack and decision.allow_pack_overlap",
            studio,
        )
        self.assertIn('"RECOVERY"', studio)

    def test_neural_minimum_workset_is_checked_in_preflight_and_runtime(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        self.assertIn("minimum_ai_gb = neural_chunk_workset_gb(", studio)
        self.assertIn("minimum_rife_gb = neural_chunk_workset_gb(", studio)
        self.assertIn("blocking_reasons.extend(neural_ram_blockers)", studio)
        self.assertIn("minimum_ai_workset_gb = neural_chunk_workset_gb(", studio)
        self.assertIn("minimum_rife_workset_gb = neural_chunk_workset_gb(", studio)
        self.assertIn("minimum=1", studio)
        self.assertIn("lote mínimo de 2 quadros excede o envelope de RAM seguro", studio)

    def test_rife_pack_applies_adaptive_cpu_thread_budget(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        self.assertIn(
            "active_cpu_threads = decision.limit_cpu_threads(cpu_threads)",
            studio,
        )
        self.assertIn(
            '"-threads", str(active_cpu_threads)',
            studio,
        )

    def test_overnight_runtime_keeps_full_cpu_and_dedicated_memory_envelope(self) -> None:
        studio = self.text("src/cinepulse/studio.py")
        scheduler = self.text("src/cinepulse/resource_scheduler.py")
        self.assertIn('"overnight"', scheduler)
        self.assertIn('machine_mode = (', studio)
        self.assertIn('"overnight"', studio)
        self.assertIn('dedicated=(machine_mode in {"dedicated", "overnight"})', studio)

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
