from __future__ import annotations

import unittest

from cinepulse.color_pipeline import build_color_pipeline
from cinepulse.media_profile import ColorProfile
from cinepulse.studio import VideoOptimizerStudio


class ColorPipelineTests(unittest.TestCase):
    def hdr10(self, *, color_range: str = "tv") -> ColorProfile:
        return ColorProfile("bt2020", "smpte2084", "bt2020nc", color_range, "yuv420p10le", 10, True)

    def sdr10(self, *, color_range: str = "tv") -> ColorProfile:
        return ColorProfile("bt709", "bt709", "bt709", color_range, "yuv420p10le", 10, False)

    def test_clean_hdr_path_preserves_hdr_and_10bit(self):
        plan = build_color_pipeline(
            self.hdr10(), effects_active=False, transition_active=False,
            enhancement_mode="preserve", rife_active=False,
        )
        self.assertTrue(plan.preserves_hdr)
        self.assertEqual(plan.working_pix_fmt, "yuv420p10le")
        self.assertEqual(plan.output.primaries, "bt2020")
        self.assertEqual(plan.output.transfer, "smpte2084")
        self.assertTrue(plan.needs_lossless_intermediate)

    def test_hdr_vfx_path_tonemaps_once_to_bt709_10bit(self):
        plan = build_color_pipeline(
            self.hdr10(), effects_active=True, transition_active=False,
            enhancement_mode="preserve", rife_active=False,
        )
        self.assertTrue(plan.tone_maps_to_sdr)
        self.assertEqual(plan.working.bit_depth, 10)
        self.assertEqual(plan.output.primaries, "bt709")
        chain = plan.tone_map_filter()
        self.assertIn("t=linear", chain)
        self.assertIn("tonemap=tonemap=mobius", chain)
        self.assertIn("dither=error_diffusion", chain)
        self.assertIn("p=bt709:t=bt709:m=bt709", chain)
        self.assertNotIn("smpte2084:colorspace=bt709", chain)

    def test_hdr_realesrgan_is_sdr_8bit_not_fake_hdr_or_fake_10bit(self):
        plan = build_color_pipeline(
            self.hdr10(), effects_active=False, transition_active=False,
            enhancement_mode="realesrgan", rife_active=False,
        )
        self.assertTrue(plan.tone_maps_to_sdr)
        self.assertEqual(plan.final_pix_fmt, "yuv420p")
        self.assertFalse(plan.output.hdr)
        self.assertTrue(plan.precision_reduction)

    def test_sdr10_rife_reduces_with_explicit_dithering(self):
        plan = build_color_pipeline(
            self.sdr10(), effects_active=False, transition_active=False,
            enhancement_mode="preserve", rife_active=True,
        )
        self.assertFalse(plan.output.hdr)
        self.assertEqual(plan.working.bit_depth, 8)
        self.assertTrue(plan.precision_reduction)
        self.assertIn("dither=error_diffusion", plan.precision_filter())

    def test_sdr10_without_neural_stage_stays_10bit(self):
        plan = build_color_pipeline(
            self.sdr10(), effects_active=False, transition_active=False,
            enhancement_mode="lanczos", rife_active=False,
        )
        self.assertEqual(plan.working.bit_depth, 10)
        self.assertFalse(plan.precision_reduction)
        self.assertEqual(plan.final_pix_fmt, "yuv420p10le")

    def test_full_range_is_preserved_on_clean_sdr_path(self):
        plan = build_color_pipeline(
            self.sdr10(color_range="pc"), effects_active=False, transition_active=False,
            enhancement_mode="preserve", rife_active=False,
        )
        self.assertEqual(plan.output.range, "pc")
        self.assertIn("range=full", plan.setparams_filter(output=True))
        self.assertEqual(plan.metadata_args(output=True)[-1], "pc")

    def test_color_critical_intermediate_uses_ffv1(self):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        plan = build_color_pipeline(
            self.sdr10(), effects_active=False, transition_active=False,
            enhancement_mode="preserve", rife_active=False,
        )
        args = studio._intermediate_encoder(1920, 1080, True, plan)
        self.assertIn("ffv1", args)
        self.assertIn("yuv420p10le", args)

    def test_sdr8_final_is_not_falsely_promoted_to_main10(self):
        studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)
        studio._nvenc = False
        source = ColorProfile("bt709", "bt709", "bt709", "tv", "yuv420p", 8, False)
        plan = build_color_pipeline(
            source, effects_active=False, transition_active=False,
            enhancement_mode="preserve", rife_active=False,
        )
        args = studio._final_encoder(1920, 1080, 60, False, True, plan)
        self.assertIn("yuv420p", args)
        self.assertNotIn("yuv420p10le", args)


if __name__ == "__main__":
    unittest.main()
