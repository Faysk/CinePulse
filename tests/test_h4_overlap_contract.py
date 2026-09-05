from __future__ import annotations

import inspect
import unittest

from cinepulse.pipeline_budget import derive_pipeline_budget
from cinepulse.studio import VideoOptimizerStudio


class H4OverlapContractTests(unittest.TestCase):
    def test_overlap_is_opt_in_at_neural_method_boundaries(self) -> None:
        upscale = inspect.signature(VideoOptimizerStudio._enhance_clip_ai)
        rife = inspect.signature(VideoOptimizerStudio._interpolate_rife)
        self.assertFalse(upscale.parameters["overlap_extract"].default)
        self.assertFalse(upscale.parameters["overlap_pack"].default)
        self.assertFalse(rife.parameters["overlap_extract"].default)

    def test_unknown_vram_never_enables_pack_overlap(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=32.0,
            vram_free_mb=None,
            scratch_free_gb=200.0,
            scratch_write_mbps=1800.0,
            dedicated=True,
        )
        self.assertFalse(budget.overlap_pack)
        self.assertLessEqual(budget.chunk_budget_gb, 4.0)
        self.assertLessEqual(budget.max_inflight_chunks, 2)

    def test_slow_scratch_keeps_pipeline_sequential(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=32.0,
            vram_free_mb=7000.0,
            scratch_free_gb=200.0,
            scratch_write_mbps=120.0,
            dedicated=True,
        )
        self.assertFalse(budget.overlap_extract)
        self.assertFalse(budget.overlap_pack)
        self.assertEqual(1, budget.max_inflight_chunks)

    def test_healthy_dedicated_budget_has_hard_three_workset_ceiling(self) -> None:
        budget = derive_pipeline_budget(
            "realesrgan",
            ram_available_gb=48.0,
            vram_free_mb=7000.0,
            scratch_free_gb=500.0,
            scratch_write_mbps=1800.0,
            dedicated=True,
        )
        self.assertTrue(budget.overlap_extract)
        self.assertTrue(budget.overlap_pack)
        self.assertEqual(3, budget.max_inflight_chunks)

    def test_realesrgan_pack_waits_before_reusing_pack_slot(self) -> None:
        source = inspect.getsource(VideoOptimizerStudio._enhance_clip_ai)
        wait = source.index("packed_result = packed_task.wait()")
        append = source.index("chunks.append(packed_video)", wait)
        cleanup = source.index("safe_rmtree(packed_dir)", append)
        new_pack = source.index("pack = (chunk_index, chunk_dir, chunk_video, packed_task)", cleanup)
        self.assertLess(wait, append)
        self.assertLess(append, cleanup)
        self.assertLess(cleanup, new_pack)
        self.assertIn("if not packed_video.is_file() or packed_video.stat().st_size <= 0", source)


if __name__ == "__main__":
    unittest.main()
