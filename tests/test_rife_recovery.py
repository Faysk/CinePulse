from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from cinepulse.hardware import HardwareProfile
import cinepulse.rife_recovery as rife_recovery
from cinepulse.rife_recovery import (
    acceptable_segment_frame_counts,
    ai_cache_key,
    concat_manifest,
    contiguous_segments,
    frame_count_from_container_duration,
    original_target_counts,
    recovery_cpu_threads,
    recovery_gpu_index,
    recovery_uses_uhd,
    remaining_schedule,
    source_chunk_counts,
    without_faststart,
)


class RifeRecoveryTests(unittest.TestCase):
    def test_recovery_master_concat_does_not_use_duration_clip(self) -> None:
        source = Path(rife_recovery.__file__).read_text(encoding="utf-8")
        start = source.index("def concatenate_master(")
        end = source.index("\ndef _final_filter(", start)
        block = source[start:end]
        self.assertNotIn('"-t"', block)
        self.assertIn("inspect_matroska_segment(partial)", block)
        self.assertIn("contract.total_target_frames", block)

    def test_without_faststart_preserves_other_muxer_arguments(self) -> None:
        self.assertEqual(
            without_faststart(["-tag:v", "hvc1", "-movflags", "+faststart"]),
            ["-tag:v", "hvc1"],
        )
        self.assertEqual(
            without_faststart(["-movflags", "+frag_keyframe+faststart"]),
            ["-movflags", "+frag_keyframe"],
        )

    def test_concat_manifest_uses_exact_frame_count_timeline(self) -> None:
        manifest = concat_manifest(
            [Path("segment_00001.mkv"), Path("segment_00002.mkv")],
            [16, 17],
            120.0,
        )
        self.assertIn("duration 0.133333333333", manifest)
        self.assertIn("duration 0.141666666667", manifest)
        self.assertEqual(manifest.count("file '"), 2)

    def test_matroska_duration_recovers_redistributed_frame_count(self) -> None:
        self.assertEqual(frame_count_from_container_duration(0.133, 120.0), 16)
        self.assertEqual(frame_count_from_container_duration(0.141, 120.0), 17)

    def test_recovery_accepts_legacy_and_cumulative_chunk_counts(self) -> None:
        counts = [2, 2]
        legacy = original_target_counts(counts, 100.0, 129.0)
        distributed = remaining_schedule(
            source_counts=counts,
            completed_chunks=0,
            completed_target_frames=0,
            total_target_frames=5,
        )
        self.assertEqual([3, 3], legacy)
        self.assertEqual([2, 3], [item.target_frames for item in distributed])
        self.assertEqual(
            {2, 3, 4},
            acceptable_segment_frame_counts(legacy[0], distributed[0].target_frames),
        )

    def test_recovery_uses_full_detected_cpu_instead_of_legacy_cap(self) -> None:
        with mock.patch("cinepulse.rife_recovery.os.cpu_count", return_value=28):
            self.assertEqual(28, recovery_cpu_threads(4))

    def test_recovery_cpu_falls_back_to_legacy_value_when_detection_is_unavailable(self) -> None:
        with mock.patch("cinepulse.rife_recovery.os.cpu_count", return_value=None):
            self.assertEqual(4, recovery_cpu_threads(4))
            self.assertEqual(1, recovery_cpu_threads(None))

    def test_recovery_uses_detected_gpu_index(self) -> None:
        hardware = HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 2)
        with mock.patch("cinepulse.rife_recovery.detect_hardware", return_value=hardware):
            self.assertEqual(2, recovery_gpu_index())

    def test_recovery_uhd_flag_matches_geometry(self) -> None:
        self.assertFalse(recovery_uses_uhd(1920, 1080))
        self.assertFalse(recovery_uses_uhd(2560, 1440))
        self.assertTrue(recovery_uses_uhd(3840, 2160))
        self.assertTrue(recovery_uses_uhd(7680, 4320))

    def test_source_chunks_merge_one_frame_tail(self) -> None:
        counts = source_chunk_counts(21745, 8)
        self.assertEqual(len(counts), 2718)
        self.assertEqual(counts[-2:], [8, 9])
        self.assertEqual(sum(counts), 21745)

    def test_remaining_schedule_recovers_exact_target_frame_count(self) -> None:
        counts = source_chunk_counts(21745, 8)
        original = original_target_counts(counts, 60000 / 1001, 120.0)
        completed = 754
        completed_target = sum(original[:completed])
        schedule = remaining_schedule(
            source_counts=counts,
            completed_chunks=completed,
            completed_target_frames=completed_target,
            total_target_frames=43533,
        )
        self.assertEqual(len(schedule), len(counts) - completed)
        self.assertEqual(sum(item.target_frames for item in schedule), 43533 - completed_target)
        self.assertEqual(schedule[0].index, 755)
        self.assertEqual(schedule[0].source_start, 6032)
        self.assertTrue(all(item.target_frames in {16, 17, 18} for item in schedule))

    def test_contiguous_segments_rejects_a_gap(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "segment_00001.mkv").touch()
            (root / "segment_00003.mkv").touch()
            with self.assertRaisesRegex(RuntimeError, "Sequencia"):
                contiguous_segments(root)

    def test_cache_key_matches_studio_identity_contract(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            model = root / "model.bin"
            source.write_bytes(b"source")
            model.write_bytes(b"model")
            actual = ai_cache_key(
                source, model, start_time=0.0, duration=12.5,
                source_fps=60000 / 1001, source_width=3840, source_height=2160,
            )
            source_stat = source.stat()
            model_stat = model.stat()
            identity = {
                "path": str(source.resolve()), "size": source_stat.st_size,
                "mtime": source_stat.st_mtime_ns, "start": 0.0, "duration": 12.5,
                "fps": round(60000 / 1001, 5), "width": 3840, "height": 2160,
                "model_size": model_stat.st_size, "model_mtime": model_stat.st_mtime_ns,
                "scale": 2,
            }
            expected = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:24]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
