from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "src" / "cinepulse" / "studio.py"
QUALITY_VIEW = ROOT / "src" / "cinepulse" / "ui" / "quality_view.py"
RIFE = ROOT / "src" / "cinepulse" / "rife_safe_runner.py"
RIFE_ENGINE = ROOT / "src" / "cinepulse" / "rife_engine.py"
RIFE_RECOVERY = ROOT / "src" / "cinepulse" / "rife_recovery.py"
VFX = ROOT / "src" / "cinepulse" / "vfx.py"


class FullUtilizationRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.studio = STUDIO.read_text(encoding="utf-8")
        cls.quality = QUALITY_VIEW.read_text(encoding="utf-8")
        cls.rife = RIFE.read_text(encoding="utf-8")
        cls.rife_engine = RIFE_ENGINE.read_text(encoding="utf-8")
        cls.rife_recovery = RIFE_RECOVERY.read_text(encoding="utf-8")
        cls.vfx = VFX.read_text(encoding="utf-8")

    def test_worker_has_no_removed_headroom_local_reference(self) -> None:
        self.assertNotIn("neural_headroom", self.studio)
        self.assertNotIn("measure_resource_headroom(", self.studio)
        self.assertIn("vram_free_mb=None", self.studio)

    def test_runtime_settings_always_canonicalize_cpu_to_full_machine(self) -> None:
        self.assertIn(
            'cpu_threads=max(1, int(self._hardware.cpu_threads))',
            self.studio,
        )
        self.assertIn(
            'clean["cpu_threads"] = default_cpu_threads(os.cpu_count() or 4)',
            self.studio,
        )
        self.assertIn(
            '"cpu_threads": max(1, int(self._hardware.cpu_threads))',
            self.studio,
        )
        self.assertNotIn('(self.cpu_threads, "cpu_threads")', self.studio)
        self.assertNotIn('(self.cpu_threads, settings.cpu_threads)', self.studio)

    def test_quality_ui_does_not_offer_fake_cpu_throttling_controls(self) -> None:
        self.assertNotIn("Threads CPU", self.quality)
        self.assertNotIn("Perfil de utilização", self.quality)
        self.assertNotIn("MACHINE_PROFILES", self.quality)
        self.assertNotIn("profile_for_threads", self.quality)
        self.assertNotIn("machine_budget", self.quality)
        self.assertIn("utilização total", self.quality)
        self.assertIn("falhar/OOM", self.quality)

    def test_integrity_fallback_contract_is_still_visible(self) -> None:
        self.assertIn("retry_policy = conservative_policy", self.studio)
        self.assertIn("sem nova medição de recursos", self.studio)
        self.assertIn("gpu_media_runtime_disabled = True", self.studio)
        self.assertIn('policy == conservative_policy and policy.pipeline != "1:1:1"', self.studio)
        self.assertIn("load_jobs=1", self.studio)
        self.assertIn("process_jobs=1", self.studio)
        self.assertIn("save_jobs=1", self.studio)

    def test_rife_uses_failure_driven_serial_fallback_and_unique_staging(self) -> None:
        self.assertIn('current.jobs == "1:1:1"', self.rife)
        self.assertIn('jobs="1:1:1"', self.rife)
        self.assertIn("time.time_ns()", self.rife)
        self.assertNotIn("vram_free_mb(", self.rife)

    def test_multi_gpu_routes_stay_pinned_to_selected_adapter(self) -> None:
        self.assertGreaterEqual(
            self.studio.count("gpu_index=self._hardware.gpu_index"),
            4,
        )
        self.assertIn('"--gpu-index"', self.rife_engine)
        self.assertIn("gpu_index=args.gpu_index", self.rife)
        self.assertIn(
            "rife_gpu_index = -1 if contract.use_cpu else contract.gpu_index",
            self.rife_recovery,
        )
        self.assertIn('"-g", str(rife_gpu_index)', self.rife_recovery)
        self.assertIn("gpu_index=max(0, contract.gpu_index)", self.rife_recovery)

    def test_rife_chunking_enforces_exact_cumulative_target_count(self) -> None:
        self.assertIn("distributed_chunk_target_count(", self.studio)
        self.assertIn("timed_concat_manifest(chunks, chunk_frame_counts, target_fps)", self.studio)
        self.assertIn("produced_target != total_target_count", self.studio)
        self.assertIn("RIFE terminou fora da contagem alvo", self.studio)
        self.assertNotIn("round(chunk_duration * target_fps)", self.studio)

    def test_rife_master_concat_is_not_duration_clipped(self) -> None:
        self.assertIn("master_quality = inspect_matroska_segment(interpolated)", self.studio)
        self.assertIn("master_quality.packet_count != total_target_count", self.studio)
        self.assertIn("Master de recuperacao existente nao cumpre o contrato", self.rife_recovery)
        self.assertIn("master_quality.packet_count == contract.total_target_frames", self.rife_recovery)
        self.assertIn("Master concatenado tem", self.rife_recovery)
        self.assertNotIn(
            '"-c", "copy",\n                "-t", f"{duration:.6f}"',
            self.studio,
        )
        self.assertNotIn(
            '"-c", "copy", "-t", f"{contract.duration:.6f}"',
            self.rife_recovery,
        )

    def test_final_cfr_delivery_is_frame_bound_not_timestamp_clipped(self) -> None:
        self.assertIn(
            "final_target_frames = max(1, int(round(project_duration * target_fps)))",
            self.studio,
        )
        self.assertIn('"-frames:v", str(final_target_frames)', self.studio)
        self.assertNotIn(
            '"-threads", str(stage_threads("encode", gpu_active=not settings.use_cpu and self._nvenc)), "-t"',
            self.studio,
        )
        self.assertIn(
            "output_frame_count = max(1, int(round(float(duration) * float(output_fps))))",
            self.vfx,
        )
        self.assertIn('"-frames:v", str(output_frame_count)', self.vfx)
        self.assertNotIn('command += ["-t", f"{duration:.6f}"', self.vfx)

    def test_final_verification_rejects_any_frame_count_drift(self) -> None:
        self.assertIn("frame_tolerance=0", self.studio)
        self.assertIn("if result.frame_count is None:", self.studio)
        self.assertIn("FFprobe não informou a contagem exata de quadros", self.studio)

    def test_rife_reuses_successful_fallback_across_later_chunks(self) -> None:
        self.assertIn('rife_jobs_override = ""', self.studio)
        self.assertIn("jobs_override=rife_jobs_override", self.studio)
        self.assertIn("applied_jobs_from_log(recent)", self.studio)
        self.assertIn("será reutilizada nos próximos", self.studio)
        self.assertIn("render-session failure memory override", self.rife)
        self.assertIn("selected_policy.pressure < fallback_spec.pressure", self.rife)


if __name__ == "__main__":
    unittest.main()
