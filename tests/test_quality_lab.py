from __future__ import annotations

import unittest

from cinepulse.ui.quality_lab import (
    estimate_quality_impact,
    estimated_bitrate_mbps,
    motion_description,
    scale_description,
)


class QualityLabTests(unittest.TestCase):
    def test_1080p60_without_ai_is_lightweight_reference(self) -> None:
        impact = estimate_quality_impact(
            source_width=1920,
            source_height=1080,
            source_fps=60,
            duration_seconds=60,
            target_width=1920,
            target_height=1080,
            target_fps=60,
            vram_mb=8192,
            neural_upscale=False,
            interpolation="Quadros repetidos — rápido",
        )
        self.assertEqual("Leve", impact.workload_label)
        self.assertAlmostEqual(1.0, impact.scale_ratio, places=2)
        self.assertAlmostEqual(1.0, impact.pixel_throughput_ratio, places=2)
        self.assertIsNone(impact.vram_reference_gb)
        self.assertIsNotNone(impact.output_gb)

    def test_8k120_ai_rife_is_extreme_and_exposes_vram_pressure(self) -> None:
        impact = estimate_quality_impact(
            source_width=1920,
            source_height=1080,
            source_fps=30,
            duration_seconds=120,
            target_width=7680,
            target_height=4320,
            target_fps=120,
            vram_mb=8192,
            neural_upscale=True,
            interpolation="RIFE IA — movimento natural",
        )
        self.assertEqual("Extrema", impact.workload_label)
        self.assertGreater(impact.scale_ratio, 3.9)
        self.assertGreater(impact.vram_reference_gb or 0, 8.0)
        self.assertTrue(any("VRAM" in warning for warning in impact.warnings))

    def test_output_estimate_is_deterministic(self) -> None:
        a = estimated_bitrate_mbps(3840, 2160, 60)
        b = estimated_bitrate_mbps(3840, 2160, 60)
        self.assertEqual(a, b)
        self.assertGreater(a, estimated_bitrate_mbps(1920, 1080, 60))

    def test_descriptions_do_not_promise_created_detail_or_time(self) -> None:
        self.assertIn("Ampliação", scale_description(2.0))
        text = motion_description(30.0, 60, "RIFE IA — movimento natural")
        self.assertIn("interpolação neural", text)
        self.assertNotIn("segundos de render", text)


if __name__ == "__main__":
    unittest.main()
