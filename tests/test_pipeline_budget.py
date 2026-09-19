from __future__ import annotations

import unittest

from cinepulse.pipeline_budget import derive_pipeline_budget


class PipelineBudgetTests(unittest.TestCase):
    def test_realesrgan_uses_fixed_maximum_budget_without_telemetry(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=None,
            vram_free_mb=None,
            scratch_free_gb=0.0,
            scratch_write_mbps=None,
            dedicated=False,
        )
        self.assertEqual(16.0, budget.chunk_budget_gb)
        self.assertEqual(3, budget.max_inflight_chunks)
        self.assertTrue(budget.overlap_extract)
        self.assertTrue(budget.overlap_pack)

    def test_bad_live_headroom_does_not_throttle_realesrgan(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=0.5,
            vram_free_mb=64.0,
            scratch_free_gb=0.1,
            scratch_write_mbps=1.0,
            dedicated=False,
        )
        self.assertEqual(16.0, budget.chunk_budget_gb)
        self.assertEqual(3, budget.max_inflight_chunks)
        self.assertTrue(budget.overlap_extract)
        self.assertTrue(budget.overlap_pack)

    def test_rife_uses_fixed_maximum_supported_overlap(self) -> None:
        budget = derive_pipeline_budget(
            "rife",
            ram_available_gb=None,
            vram_free_mb=None,
            scratch_free_gb=0.0,
            scratch_write_mbps=None,
            dedicated=False,
        )
        self.assertEqual(12.0, budget.chunk_budget_gb)
        self.assertEqual(2, budget.max_inflight_chunks)
        self.assertTrue(budget.overlap_extract)
        self.assertFalse(budget.overlap_pack)

    def test_profile_and_measurements_do_not_change_fixed_budget(self) -> None:
        low = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=1.0,
            vram_free_mb=100.0,
            scratch_free_gb=1.0,
            scratch_write_mbps=1.0,
            dedicated=False,
        )
        high = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=256.0,
            vram_free_mb=48_000.0,
            scratch_free_gb=5000.0,
            scratch_write_mbps=7000.0,
            dedicated=True,
        )
        self.assertEqual(low, high)

    def test_unknown_stage_is_rejected() -> None:
        with self.assertRaises(ValueError):
            derive_pipeline_budget(
                "invalid",  # type: ignore[arg-type]
                ram_available_gb=None,
                vram_free_mb=None,
                scratch_free_gb=0.0,
                scratch_write_mbps=None,
            )


if __name__ == "__main__":
    unittest.main()
