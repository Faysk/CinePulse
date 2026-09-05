from __future__ import annotations

import unittest

from cinepulse.restoration_delivery import (
    PreviewDeliveryTarget,
    assess_preview_delivery,
    estimate_frame_mib,
)


class RestorationDeliveryTests(unittest.TestCase):
    def test_4k60_is_structurally_allowed_without_physical_gate(self):
        assessment = assess_preview_delivery(PreviewDeliveryTarget(3840, 2160, 60))
        self.assertTrue(assessment.allowed)
        self.assertFalse(assessment.requires_physical_acceptance)

    def test_8k60_remains_pending_without_real_gpu_evidence(self):
        assessment = assess_preview_delivery(PreviewDeliveryTarget(7680, 4320, 60))
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.requires_physical_acceptance)
        self.assertTrue(any("Physical GPU acceptance" in warning for warning in assessment.warnings))

    def test_12k120_is_inside_preview_envelope_but_not_claimed_validated(self):
        assessment = assess_preview_delivery(PreviewDeliveryTarget(11520, 6480, 120), temporal_window=3)
        self.assertTrue(assessment.allowed)
        self.assertTrue(assessment.requires_physical_acceptance)
        self.assertGreater(assessment.estimated_working_set_mib, assessment.estimated_rgb_frame_mib)

    def test_target_above_12k_is_rejected(self):
        assessment = assess_preview_delivery(PreviewDeliveryTarget(12000, 6480, 60))
        self.assertFalse(assessment.allowed)
        self.assertTrue(any("12K" in warning for warning in assessment.warnings))

    def test_target_above_120fps_is_rejected(self):
        assessment = assess_preview_delivery(PreviewDeliveryTarget(3840, 2160, 144))
        self.assertFalse(assessment.allowed)
        self.assertTrue(any("120 fps" in warning for warning in assessment.warnings))

    def test_low_scratch_space_blocks_heavy_plan(self):
        assessment = assess_preview_delivery(
            PreviewDeliveryTarget(11520, 6480, 120),
            temporal_window=5,
            scratch_free_gib=1.0,
        )
        self.assertFalse(assessment.allowed)
        self.assertTrue(any("Scratch space" in warning for warning in assessment.warnings))

    def test_real_gpu_evidence_clears_only_acceptance_flag(self):
        assessment = assess_preview_delivery(
            PreviewDeliveryTarget(7680, 4320, 120),
            has_real_gpu_evidence=True,
        )
        self.assertTrue(assessment.allowed)
        self.assertFalse(assessment.requires_physical_acceptance)

    def test_frame_estimate_accounts_for_10bit_unpacking(self):
        eight = estimate_frame_mib(PreviewDeliveryTarget(1920, 1080, 60, bit_depth=8))
        ten = estimate_frame_mib(PreviewDeliveryTarget(1920, 1080, 60, bit_depth=10))
        self.assertAlmostEqual(ten, eight * 2.0)

    def test_invalid_target_values_are_rejected(self):
        with self.assertRaises(ValueError):
            PreviewDeliveryTarget(0, 1080, 60)
        with self.assertRaises(ValueError):
            PreviewDeliveryTarget(1920, 1080, 0)
        with self.assertRaises(ValueError):
            PreviewDeliveryTarget(1920, 1080, 60, bit_depth=9)


if __name__ == "__main__":
    unittest.main()
