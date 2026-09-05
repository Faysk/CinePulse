from __future__ import annotations

import unittest

from cinepulse.pipeline_budget import derive_pipeline_budget


class PipelineBudgetTests(unittest.TestCase):
    def test_unknown_telemetry_never_expands_past_legacy_budget(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=None,
            vram_free_mb=None,
            scratch_free_gb=100.0,
            scratch_write_mbps=None,
        )
        self.assertLessEqual(budget.chunk_budget_gb, 4.0)
        self.assertEqual(budget.max_inflight_chunks, 1)

    def test_missing_vram_never_expands_past_legacy_budget(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=64.0,
            vram_free_mb=None,
            scratch_free_gb=1000.0,
            scratch_write_mbps=1800.0,
            dedicated=True,
        )
        self.assertLessEqual(budget.chunk_budget_gb, 4.0)
        self.assertFalse(budget.overlap_pack)

    def test_fast_dedicated_machine_allows_bounded_overlap(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=40.0,
            vram_free_mb=12000,
            scratch_free_gb=500.0,
            scratch_write_mbps=1800.0,
            dedicated=True,
        )
        self.assertTrue(budget.overlap_extract)
        self.assertTrue(budget.overlap_pack)
        self.assertEqual(budget.max_inflight_chunks, 3)
        self.assertLessEqual(budget.chunk_budget_gb, 8.0)

    def test_slow_scratch_disables_overlap_even_with_ram(self) -> None:
        budget = derive_pipeline_budget(
            "rife",
            ram_available_gb=32.0,
            vram_free_mb=12000,
            scratch_free_gb=300.0,
            scratch_write_mbps=120.0,
            dedicated=True,
        )
        self.assertFalse(budget.overlap_extract)
        self.assertFalse(budget.overlap_pack)
        self.assertEqual(budget.max_inflight_chunks, 1)

    def test_rife_budget_is_tighter_than_realesrgan(self) -> None:
        common = dict(
            ram_available_gb=64.0,
            vram_free_mb=24000,
            scratch_free_gb=500.0,
            scratch_write_mbps=1200.0,
            dedicated=True,
        )
        ai = derive_pipeline_budget("realesrgan", **common)
        rife = derive_pipeline_budget("rife", **common)
        self.assertLessEqual(rife.chunk_budget_gb, ai.chunk_budget_gb)
        self.assertLessEqual(rife.chunk_budget_gb, 6.0)

    def test_inflight_queue_is_hard_bounded(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=256.0,
            vram_free_mb=48000,
            scratch_free_gb=5000.0,
            scratch_write_mbps=7000.0,
            dedicated=True,
        )
        self.assertLessEqual(budget.max_inflight_chunks, 3)


if __name__ == "__main__":
    unittest.main()
