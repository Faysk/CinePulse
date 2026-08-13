from __future__ import annotations

import unittest

from cinepulse.render_plan import PlanInput, build_render_plan, risks_as_warnings, spatial_scale_factor


class RenderPlanTests(unittest.TestCase):
    def _plan(self, **overrides):
        values = dict(
            source_width=1920,
            source_height=1080,
            source_fps=60.0,
            target_width=3840,
            target_height=2160,
            target_fps=60.0,
            project_mode="music",
            preview=False,
            enhancement_mode="lanczos",
            interpolation_mode="ffmpeg",
            effects_active=False,
            transition_active=False,
            use_cpu=False,
            fit_mode="contain",
            source_hdr=False,
            source_bit_depth=8,
            source_pixel_format="yuv420p 8-bit",
            source_primaries="bt709",
            source_transfer="bt709",
            source_space="bt709",
            source_range="tv",
            realesrgan_available=True,
            rife_available=True,
            auto_loop_may_add_transition=False,
        )
        values.update(overrides)
        return build_render_plan(PlanInput(**values))

    def test_8k120_to_1080p120_preserves_master_resolution_and_fps(self):
        plan = self._plan(
            source_width=7680,
            source_height=4320,
            source_fps=120.0,
            target_width=1920,
            target_height=1080,
            target_fps=120.0,
            enhancement_mode="preserve",
            interpolation_mode="rife",
        )
        master = plan.step("master")
        self.assertTrue(master.runs)
        self.assertEqual((master.output_spec.width, master.output_spec.height, master.output_spec.fps), (1920, 1080, 120.0))
        self.assertFalse(plan.step("rife_base").attempts)
        self.assertFalse(plan.step("rife_final").attempts)
        codes = {risk.code for risk in plan.risks}
        self.assertNotIn("CP-001", codes)
        self.assertNotIn("CP-002", codes)
        self.assertNotIn("CP-001/CP-002", codes)

    def test_original_mode_without_visual_stages_can_skip_master(self):
        plan = self._plan(
            project_mode="original",
            source_width=3840,
            source_height=2160,
            target_width=3840,
            target_height=2160,
            enhancement_mode="preserve",
        )
        self.assertFalse(plan.needs_master)
        self.assertFalse(plan.step("master").runs)

    def test_realesrgan_is_skipped_when_destination_does_not_need_upscale(self):
        plan = self._plan(
            source_width=7680,
            source_height=4320,
            target_width=1920,
            target_height=1080,
            enhancement_mode="realesrgan",
        )
        ai = plan.step("enhancement")
        self.assertFalse(ai.attempts)
        self.assertEqual((ai.output_spec.width, ai.output_spec.height), (7680, 4320))
        self.assertNotIn("CP-004", {risk.code for risk in plan.risks})

    def test_realesrgan_runs_when_contain_framing_requires_upscale(self):
        plan = self._plan(
            source_width=1280,
            source_height=720,
            target_width=3840,
            target_height=2160,
            enhancement_mode="realesrgan",
        )
        ai = plan.step("enhancement")
        self.assertTrue(ai.runs)
        self.assertEqual((ai.output_spec.width, ai.output_spec.height), (2560, 1440))
        self.assertTrue(ai.materializes_frames)

    def test_portrait_contain_does_not_false_positive_ai_upscale(self):
        plan = self._plan(
            source_width=1920,
            source_height=1080,
            target_width=1080,
            target_height=1920,
            fit_mode="contain",
            enhancement_mode="realesrgan",
        )
        self.assertFalse(plan.step("enhancement").attempts)

    def test_portrait_cover_correctly_detects_ai_upscale_need(self):
        plan = self._plan(
            source_width=1920,
            source_height=1080,
            target_width=1080,
            target_height=1920,
            fit_mode="cover",
            enhancement_mode="realesrgan",
        )
        self.assertTrue(plan.step("enhancement").attempts)

    def test_rife_is_one_shot_after_master(self):
        plan = self._plan(
            source_width=1280,
            source_height=720,
            source_fps=24.0,
            target_width=3840,
            target_height=2160,
            target_fps=60.0,
            enhancement_mode="lanczos",
            interpolation_mode="rife",
        )
        self.assertFalse(plan.step("rife_base").attempts)
        self.assertEqual(plan.step("master").output_spec.fps, 24.0)
        self.assertTrue(plan.step("rife_final").runs)
        self.assertEqual(plan.step("rife_final").output_spec.fps, 60.0)
        self.assertEqual(plan.metadata["rife_calls_planned"], 1)

    def test_rife_is_skipped_when_source_already_meets_target_fps(self):
        plan = self._plan(
            source_fps=120.0,
            target_fps=120.0,
            interpolation_mode="rife",
        )
        self.assertFalse(plan.step("rife_base").attempts)
        self.assertFalse(plan.step("rife_final").attempts)
        self.assertEqual(plan.metadata["rife_calls_planned"], 0)

    def test_lower_target_fps_is_an_intentional_downsample_not_rife(self):
        plan = self._plan(
            source_fps=120.0,
            target_fps=60.0,
            interpolation_mode="rife",
        )
        self.assertEqual(plan.step("master").output_spec.fps, 60.0)
        self.assertFalse(plan.step("rife_final").attempts)

    def test_ffmpeg_interpolation_reaches_target_in_master_once(self):
        plan = self._plan(
            source_fps=24.0,
            target_fps=60.0,
            interpolation_mode="ffmpeg",
        )
        self.assertEqual(plan.step("master").output_spec.fps, 60.0)
        self.assertFalse(plan.step("rife_final").attempts)

    def test_vfx_is_target_aware_and_preserves_base_cadence(self):
        plan = self._plan(
            source_fps=120.0,
            target_fps=120.0,
            effects_active=True,
            target_width=7680,
            target_height=4320,
        )
        vfx = plan.step("vfx")
        self.assertTrue(vfx.runs)
        self.assertEqual(vfx.output_spec.fps, 120.0)
        self.assertEqual((vfx.internal_spec.width, vfx.internal_spec.height, vfx.internal_spec.fps), (3840, 2160, 120.0))
        self.assertNotIn("CP-003", {risk.code for risk in plan.risks})
        self.assertIn("CI-P3-VFX-8K", {risk.code for risk in plan.risks})

    def test_hdr_clean_path_uses_10bit_master_without_cp007(self):
        plan = self._plan(
            source_hdr=True,
            source_bit_depth=10,
            source_pixel_format="yuv420p10le 10-bit",
            source_primaries="bt2020",
            source_transfer="smpte2084",
            source_space="bt2020nc",
            source_range="tv",
        )
        self.assertNotIn("CP-007", {risk.code for risk in plan.risks})
        self.assertIn("yuv420p10le", plan.step("master").output_spec.pixel_format)
        self.assertTrue(plan.metadata["color_preserves_hdr"])
        self.assertFalse(plan.step("master").lossy_intermediate)

    def test_hdr_with_vfx_is_explicitly_tonemapped_to_sdr(self):
        plan = self._plan(
            source_hdr=True,
            source_bit_depth=10,
            source_pixel_format="yuv420p10le 10-bit",
            source_primaries="bt2020",
            source_transfer="smpte2084",
            source_space="bt2020nc",
            source_range="tv",
            effects_active=True,
        )
        self.assertEqual(plan.metadata["color_intent"], "tone_map_sdr")
        self.assertTrue(plan.metadata["color_tone_maps_to_sdr"])
        self.assertIn("CI-P4-HDR-SDR", {risk.code for risk in plan.risks})
        self.assertNotIn("CP-007", {risk.code for risk in plan.risks})
        self.assertIn("bt709", plan.step("vfx").output_spec.pixel_format)

    def test_sdr10_with_rife_declares_explicit_8bit_neural_boundary(self):
        plan = self._plan(
            source_bit_depth=10,
            source_pixel_format="yuv420p10le 10-bit",
            source_fps=24,
            target_fps=60,
            interpolation_mode="rife",
        )
        self.assertEqual(plan.metadata["color_final_pix_fmt"], "yuv420p")
        self.assertIn("CI-P4-AI-8BIT", {risk.code for risk in plan.risks})
        self.assertNotIn("CP-007", {risk.code for risk in plan.risks})

    def test_preserve_and_lanczos_have_distinct_policy(self):
        preserve = self._plan(
            source_width=1280,
            source_height=720,
            target_width=3840,
            target_height=2160,
            enhancement_mode="preserve",
        )
        lanczos = self._plan(
            source_width=1280,
            source_height=720,
            target_width=3840,
            target_height=2160,
            enhancement_mode="lanczos",
        )
        self.assertIn("não serão ampliados", preserve.step("enhancement").reason)
        self.assertIn("redimensionamento espacial explícito", lanczos.step("enhancement").reason)
        self.assertIn("CI-P2-PRESERVE", {risk.code for risk in preserve.risks})
        self.assertNotIn("CP-006", {risk.code for risk in preserve.risks})
        self.assertNotIn("CP-006", {risk.code for risk in lanczos.risks})

    def test_spatial_scale_factor_respects_contain_and_cover(self):
        self.assertAlmostEqual(spatial_scale_factor(1920, 1080, 1080, 1920, "contain"), 0.5625)
        self.assertAlmostEqual(spatial_scale_factor(1920, 1080, 1080, 1920, "cover"), 1920 / 1080)

    def test_auto_loop_cut_is_explicitly_conditional_in_preflight_plan(self):
        plan = self._plan(auto_loop_may_add_transition=True)
        transition = plan.step("transition")
        self.assertEqual(transition.status, "conditional")
        self.assertIn("pode promover", transition.reason)

    def test_fingerprint_and_serialization_are_deterministic(self):
        first = self._plan()
        second = self._plan()
        self.assertEqual(first.fingerprint, second.fingerprint)
        payload = first.to_dict()
        self.assertEqual(payload["fingerprint"], first.fingerprint)
        self.assertEqual(payload["architecture_version"], "core-integrity-phase8-runtime-distribution")
        self.assertEqual(payload["metadata"]["resolved_audit_codes"], ["CP-001", "CP-002", "CP-003", "CP-004", "CP-005", "CP-006", "CP-007", "CP-008", "CP-009", "CP-010", "CP-012", "CP-013", "CP-014", "CP-015", "CP-016", "CP-017", "CP-018", "CP-021", "CP-022", "CP-023", "CP-029", "CP-030", "CP-031"])
        self.assertEqual(payload["metadata"]["pending_audit_codes"], ["CP-011", "CP-019", "CP-020", "CP-027", "CP-032", "CP-033"])

    def test_user_lines_disclose_device_per_running_step(self):
        plan = self._plan(effects_active=True)
        lines = plan.user_lines()
        self.assertTrue(any("dispositivo:" in line for line in lines))
        self.assertTrue(any("CPU" in line or "GPU" in line for line in lines if "dispositivo:" in line))

    def test_delivery_step_is_part_of_render_plan(self):
        plan = self._plan(output_suffix=".webm", delivery_profile="Web")
        self.assertTrue(plan.step("delivery").runs)
        self.assertEqual(plan.metadata["delivery_container"], "WebM")
        self.assertEqual(plan.metadata["delivery_video_codec"], "VP9")
        self.assertEqual(plan.metadata["delivery_audio_codec"], "Opus")

    def test_unstable_240fps_is_a_critical_delivery_risk(self):
        plan = self._plan(target_fps=240.0)
        risk = next(item for item in plan.risks if item.code == "CP-009-FPS")
        self.assertEqual(risk.severity, "critical")

    def test_risk_warnings_keep_audit_codes_visible(self):
        plan = self._plan(effects_active=True, target_width=7680, target_height=4320)
        messages = risks_as_warnings(plan.risks)
        self.assertTrue(any("CI-P3-VFX-8K" in message for message in messages))
        self.assertFalse(any("CP-003" in message for message in messages))
        self.assertTrue(all(message.startswith("[") for message in messages))

    def test_invalid_media_dimensions_are_rejected_early(self):
        with self.assertRaises(ValueError):
            self._plan(source_width=0)
        with self.assertRaises(ValueError):
            self._plan(target_fps=0)
        with self.assertRaises(ValueError):
            self._plan(fit_mode="invalid")


if __name__ == "__main__":
    unittest.main()
