from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

from cinepulse.render_plan import FrameSpec, PlanInput, build_render_plan
from cinepulse.storage_engine import (
    cache_usage_bytes,
    choose_chunk_frames,
    enforce_cache_quota,
    estimate_storage,
    resolve_scratch_dir,
    probe_scratch,
    reset_directory_for_retry,
    touch_cache_entry,
    neural_chunk_workset_gb,
    _compressed_gb,
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

    def test_realesrgan_can_drop_to_one_frame_when_budget_is_tight(self):
        source = FrameSpec(7680, 4320, 30)
        target = FrameSpec(15360, 8640, 30)
        frames = choose_chunk_frames(
            source,
            target,
            budget_gb=0.5,
            minimum=1,
        )
        self.assertEqual(frames, 1)
        self.assertGreater(
            neural_chunk_workset_gb(source, target, 2),
            neural_chunk_workset_gb(source, target, 1),
        )

    def test_rife_minimum_two_frames_can_exceed_tiny_budget_and_is_measurable(self):
        source = FrameSpec(11520, 6480, 30)
        target = FrameSpec(11520, 6480, 60)
        minimum = neural_chunk_workset_gb(
            source,
            target,
            2,
            output_frames_per_input=2.0,
        )
        self.assertGreater(minimum, 0.5)
        self.assertEqual(
            choose_chunk_frames(
                source,
                target,
                budget_gb=0.5,
                output_frames_per_input=2.0,
            ),
            2,
        )

    def test_chunk_size_shrinks_for_larger_frames(self):
        small = choose_chunk_frames(FrameSpec(640, 360, 30), FrameSpec(1280, 720, 30), budget_gb=1)
        large = choose_chunk_frames(FrameSpec(3840, 2160, 30), FrameSpec(7680, 4320, 30), budget_gb=1)
        self.assertGreater(small, large)
        self.assertGreaterEqual(large, 2)

    def test_large_ram_budget_can_exceed_legacy_240_frame_cap(self):
        ai = choose_chunk_frames(
            FrameSpec(1280, 720, 30),
            FrameSpec(2560, 1440, 30),
            budget_gb=16.0,
        )
        rife = choose_chunk_frames(
            FrameSpec(1920, 1080, 30),
            FrameSpec(1920, 1080, 60),
            budget_gb=12.0,
            output_frames_per_input=2.0,
        )
        self.assertGreater(ai, 240)
        self.assertLessEqual(ai, 480)
        self.assertGreater(rife, 240)
        self.assertLessEqual(rife, 480)

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
        self.assertIn("rife_base", keys)
        self.assertNotIn("rife_final", keys)
        self.assertGreater(estimate.peak_scratch_gb, 0)
        self.assertLessEqual(estimate.ai_chunk_frames, 480)

    def test_separate_dynamic_ai_and_rife_budgets_are_reflected_in_preflight(self):
        plan = self._plan(
            source_width=1920, source_height=1080, source_fps=30,
            target_width=3840, target_height=2160, target_fps=60,
        )
        legacy = estimate_storage(plan, duration=30, output_gb=1.2, chunk_budget_gb=4.0)
        dynamic = estimate_storage(
            plan, duration=30, output_gb=1.2,
            ai_chunk_budget_gb=16.0, rife_chunk_budget_gb=12.0,
        )
        self.assertGreaterEqual(dynamic.ai_chunk_frames, legacy.ai_chunk_frames)
        self.assertGreaterEqual(dynamic.rife_chunk_frames, legacy.rife_chunk_frames)
        self.assertGreaterEqual(dynamic.peak_scratch_gb, legacy.peak_scratch_gb)
        by_key = {stage.key: stage for stage in dynamic.stages}
        self.assertGreater(by_key["enhancement"].working_set_gb, 0.0)
        self.assertGreater(by_key["rife_base"].working_set_gb, 0.0)

    def test_concurrent_neural_worksets_raise_peak_scratch_reservation(self):
        plan = self._plan(
            source_width=1920, source_height=1080, source_fps=30,
            target_width=3840, target_height=2160, target_fps=60,
        )
        one = estimate_storage(
            plan, duration=30, output_gb=1.2,
            ai_chunk_budget_gb=16.0, rife_chunk_budget_gb=12.0,
            ai_inflight_chunks=1, rife_inflight_chunks=1,
        )
        overlapped = estimate_storage(
            plan, duration=30, output_gb=1.2,
            ai_chunk_budget_gb=16.0, rife_chunk_budget_gb=12.0,
            ai_inflight_chunks=3, rife_inflight_chunks=2,
        )
        self.assertGreater(overlapped.peak_scratch_gb, one.peak_scratch_gb)
        details = " ".join(stage.detail for stage in overlapped.stages)
        self.assertIn("até 3 lote(s) coexistem", details)
        self.assertIn("até 2 lote(s) coexistem", details)

    def test_neural_peak_includes_accumulated_segments_plus_live_worksets(self):
        plan = self._plan(
            source_width=1920, source_height=1080, source_fps=30,
            target_width=3840, target_height=2160, target_fps=60,
        )
        estimate = estimate_storage(
            plan,
            duration=30,
            output_gb=1.2,
            ai_chunk_budget_gb=16.0,
            rife_chunk_budget_gb=12.0,
            ai_inflight_chunks=3,
            rife_inflight_chunks=2,
        )
        by_key = {stage.key: stage for stage in estimate.stages}

        enhancement = by_key["enhancement"]
        ai_spec = plan.step("enhancement").output_spec
        self.assertIsNotNone(ai_spec)
        ai_master = _compressed_gb(ai_spec, enhancement.duration_seconds, lossless=True)
        self.assertGreaterEqual(
            enhancement.peak_scratch_gb + 1e-9,
            ai_master + enhancement.working_set_gb,
        )

        rife_base = by_key["rife_base"]
        rife_spec = plan.step("rife_base").output_spec
        self.assertIsNotNone(rife_spec)
        rife_master = _compressed_gb(rife_spec, rife_base.duration_seconds, lossless=True)
        self.assertGreaterEqual(
            rife_base.peak_scratch_gb + 1e-9,
            rife_master + rife_base.working_set_gb,
        )

    def test_inflight_storage_inputs_are_hard_capped(self):
        plan = self._plan()
        capped = estimate_storage(
            plan, duration=20, output_gb=1.0,
            ai_inflight_chunks=99, rife_inflight_chunks=99,
        )
        explicit = estimate_storage(
            plan, duration=20, output_gb=1.0,
            ai_inflight_chunks=3, rife_inflight_chunks=3,
        )
        self.assertAlmostEqual(capped.peak_scratch_gb, explicit.peak_scratch_gb, places=6)

    def test_legacy_chunk_budget_remains_backward_compatible(self):
        plan = self._plan()
        old_style = estimate_storage(plan, duration=20, output_gb=1.0, chunk_budget_gb=3.0)
        split_style = estimate_storage(
            plan, duration=20, output_gb=1.0,
            ai_chunk_budget_gb=3.0, rife_chunk_budget_gb=3.0,
        )
        self.assertEqual(old_style.ai_chunk_frames, split_style.ai_chunk_frames)
        self.assertEqual(old_style.rife_chunk_frames, split_style.rife_chunk_frames)
        self.assertAlmostEqual(old_style.peak_scratch_gb, split_style.peak_scratch_gb, places=6)

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
        self.assertAlmostEqual(long_by_key["rife_base"].duration_seconds, 10.0)
        self.assertNotIn("rife_final", long_by_key)
        self.assertAlmostEqual(long_by_key["vfx"].duration_seconds, 264.0)
        self.assertEqual(long_by_key["vfx"].persistent_gb, 0.0)
        self.assertEqual(long_by_key["vfx"].working_set_gb, 0.0)
        self.assertIn("streaming direto", long_by_key["vfx"].detail)
        self.assertLess(long.peak_scratch_gb, 100.0)
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

    def test_retry_directory_reset_removes_stale_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames"
            path.mkdir()
            (path / "stale.png").write_bytes(b"stale")
            reset_directory_for_retry(path, timeout_seconds=0.1, retry_seconds=0.001)
            self.assertTrue(path.is_dir())
            self.assertEqual([], list(path.iterdir()))

    def test_retry_directory_reset_waits_for_transient_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames"
            path.mkdir()
            (path / "stale.png").write_bytes(b"stale")
            real_rmtree = shutil.rmtree
            attempts = {"count": 0}

            def flaky_rmtree(target):
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise PermissionError("simulated Windows lock")
                real_rmtree(target)

            with mock.patch("cinepulse.storage_engine.shutil.rmtree", side_effect=flaky_rmtree):
                reset_directory_for_retry(path, timeout_seconds=0.2, retry_seconds=0.001)

            self.assertGreaterEqual(attempts["count"], 3)
            self.assertTrue(path.is_dir())
            self.assertEqual([], list(path.iterdir()))

    def test_retry_directory_reset_fails_instead_of_reusing_dirty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames"
            path.mkdir()
            (path / "stale.png").write_bytes(b"stale")
            with mock.patch(
                "cinepulse.storage_engine.shutil.rmtree",
                side_effect=PermissionError("persistent lock"),
            ):
                with self.assertRaisesRegex(RuntimeError, "diretório limpo para retry"):
                    reset_directory_for_retry(
                        path,
                        timeout_seconds=0.0,
                        retry_seconds=0.001,
                    )
            self.assertTrue((path / "stale.png").exists())

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
