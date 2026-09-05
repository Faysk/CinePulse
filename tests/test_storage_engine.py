from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from cinepulse.render_plan import FrameSpec, PlanInput, build_render_plan
from cinepulse.storage_engine import (
    cache_usage_bytes,
    choose_chunk_frames,
    enforce_cache_quota,
    estimate_storage,
    resolve_scratch_dir,
    probe_scratch,
    touch_cache_entry,
)


class StorageEngineTests(unittest.TestCase):
    def _plan(self, **overrides):
        values = dict(
            source_width=1280, source_height=720, source_fps=24.0,
            target_width=3840, target_height=2160, target_fps=60.0,
            project_mode="music", preview=False, enhancement_mode="realesrgan",
            interpolation_mode="rife", effects_active=True, transition_active=False,
            use_cpu=False, fit_mode="contain", realesrgan_available=True, rife_available=True,
            output_suffix=".mp4", delivery_profile="Automático pelo arquivo",
        )
        values.update(overrides)
        return build_render_plan(PlanInput(**values))

    def test_chunk_size_shrinks_for_larger_frames(self):
        small = choose_chunk_frames(FrameSpec(640, 360, 30), FrameSpec(1280, 720, 30), budget_gb=1)
        large = choose_chunk_frames(FrameSpec(3840, 2160, 30), FrameSpec(7680, 4320, 30), budget_gb=1)
        self.assertGreater(small, large)
        self.assertGreaterEqual(large, 2)

    def test_rife_ratio_is_part_of_chunk_budget(self):
        one_x = choose_chunk_frames(FrameSpec(1920, 1080, 24), FrameSpec(1920, 1080, 24), budget_gb=1)
        four_x = choose_chunk_frames(
            FrameSpec(1920, 1080, 24), FrameSpec(1920, 1080, 96), budget_gb=1,
            output_frames_per_input=4,
        )
        self.assertLess(four_x, one_x)

    def test_estimator_uses_render_plan_neural_stages(self):
        estimate = estimate_storage(self._plan(), duration=30, output_gb=1.2, cache_current_gb=0, cache_quota_gb=50)
        keys = {stage.key for stage in estimate.stages}
        self.assertIn("enhancement", keys)
        self.assertIn("rife_final", keys)
        self.assertGreater(estimate.peak_scratch_gb, 0)
        self.assertLessEqual(estimate.ai_chunk_frames, 240)

    def test_music_loop_uses_clip_duration_before_timeline_expansion(self):
        plan = self._plan(
            source_width=1280, source_height=720, source_fps=24,
            target_width=7680, target_height=4320, target_fps=120,
            effects_active=True, transition_active=True,
        )
        short = estimate_storage(
            plan, clip_duration=10, project_duration=10, output_gb=1.0, cache_quota_gb=50,
        )
        long = estimate_storage(
            plan, clip_duration=10, project_duration=264, output_gb=20.0, cache_quota_gb=50,
        )
        short_by_key = {stage.key: stage for stage in short.stages}
        long_by_key = {stage.key: stage for stage in long.stages}
        for key in ("enhancement", "master", "transition"):
            self.assertAlmostEqual(short_by_key[key].duration_seconds, 10.0)
            self.assertAlmostEqual(long_by_key[key].duration_seconds, 10.0)
            self.assertAlmostEqual(short_by_key[key].peak_scratch_gb, long_by_key[key].peak_scratch_gb, places=6)
        self.assertAlmostEqual(short.cache_growth_gb, long.cache_growth_gb, places=6)
        self.assertAlmostEqual(long_by_key["vfx"].duration_seconds, 264.0)
        self.assertAlmostEqual(long_by_key["rife_final"].duration_seconds, 264.0)
        self.assertGreater(long_by_key["vfx"].persistent_gb, short_by_key["vfx"].persistent_gb * 20)
        self.assertEqual(long.clip_duration_seconds, 10.0)
        self.assertEqual(long.project_duration_seconds, 264.0)

    def test_color_prepass_is_counted_at_clip_duration(self):
        plan = self._plan(
            source_bit_depth=10, source_pixel_format="yuv420p10le",
            source_primaries="bt709", source_transfer="bt709", source_space="bt709", source_range="tv",
        )
        estimate = estimate_storage(
            plan, clip_duration=8, project_duration=240, output_gb=10, cache_quota_gb=50,
        )
        by_key = {stage.key: stage for stage in estimate.stages}
        self.assertIn("color", by_key)
        self.assertAlmostEqual(by_key["color"].duration_seconds, 8.0)
        self.assertAlmostEqual(by_key["enhancement"].duration_seconds, 8.0)
        self.assertAlmostEqual(by_key["vfx"].duration_seconds, 240.0)

    def test_legacy_duration_keeps_single_timeline_compatibility(self):
        estimate = estimate_storage(self._plan(), duration=30, output_gb=1.2)
        self.assertEqual(estimate.clip_duration_seconds, 30.0)
        self.assertEqual(estimate.project_duration_seconds, 30.0)

    def test_estimator_skips_ai_for_downscale(self):
        plan = self._plan(
            source_width=7680, source_height=4320, source_fps=120,
            target_width=1920, target_height=1080, target_fps=120,
            enhancement_mode="realesrgan", interpolation_mode="rife", effects_active=False,
        )
        estimate = estimate_storage(plan, duration=10, output_gb=.2)
        self.assertNotIn("enhancement", {stage.key for stage in estimate.stages})
        self.assertNotIn("rife_final", {stage.key for stage in estimate.stages})

    def test_scratch_override_and_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(resolve_scratch_dir("", root), root.resolve())
            other = root / "other"
            self.assertEqual(resolve_scratch_dir(str(other), root), other.resolve())

    def test_cache_quota_prunes_oldest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / "old.bin"
            new = root / "new.bin"
            old.write_bytes(b"a" * 800_000)
            new.write_bytes(b"b" * 800_000)
            now = time.time()
            os.utime(old, (now - 1000, now - 1000))
            os.utime(new, (now, now))
            result = enforce_cache_quota(root, 0.001)
            self.assertGreaterEqual(result.removed_files, 1)
            self.assertFalse(old.exists())
            self.assertTrue(new.exists())

    def test_cache_quota_respects_protected_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            protected = root / "protected.bin"
            victim = root / "victim.bin"
            protected.write_bytes(b"a" * 800_000)
            victim.write_bytes(b"b" * 800_000)
            os.utime(protected, (1, 1))
            result = enforce_cache_quota(root, 0.0005, protected=(protected,))
            self.assertTrue(protected.exists())
            self.assertFalse(victim.exists())
            self.assertGreater(result.removed_bytes, 0)

    def test_touch_cache_entry_updates_recency(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.bin"
            path.write_bytes(b"x")
            os.utime(path, (1, 1))
            touch_cache_entry(path)
            self.assertGreater(path.stat().st_mtime, 1)

    def test_scratch_probe_reports_volume_and_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probe_scratch(Path(tmp), sample_mb=1, cache_seconds=0)
            self.assertTrue(result.volume)
            self.assertGreater(result.total_gb, 0)
            self.assertGreaterEqual(result.free_gb, 0)
            self.assertIsNotNone(result.write_mbps)

    def test_cache_usage_is_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "a").write_bytes(b"a" * 10)
            (root / "nested" / "b").write_bytes(b"b" * 20)
            self.assertEqual(cache_usage_bytes(root), 30)


if __name__ == "__main__":
    unittest.main()
