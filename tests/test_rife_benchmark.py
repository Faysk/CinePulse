from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.rife_benchmark import benchmark_and_record, looks_like_oom, run_candidate
from cinepulse.rife_tuning import RifePolicy, RifeSample, RifeTuningKey, RifeTuningStore


def fake_png(width: int = 64, height: int = 36) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class Result:
    def __init__(self, returncode: int = 0, stdout=b"") -> None:
        self.returncode = returncode
        self.stdout = stdout


class RifeBenchmarkTests(unittest.TestCase):
    def test_oom_detection(self) -> None:
        self.assertTrue(looks_like_oom("VK_ERROR_OUT_OF_DEVICE_MEMORY"))
        self.assertTrue(looks_like_oom("failed to allocate device buffer"))
        self.assertFalse(looks_like_oom("completed"))

    def test_candidate_requires_png_integrity_and_nonblack_samples(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "in"
            outgoing = root / "out"
            incoming.mkdir()
            for index in range(2):
                (incoming / f"{index:08d}.png").write_bytes(fake_png())

            def fake_run(command, **_kwargs):
                if "rawvideo" in command:
                    return Result(0, bytes([32]) * (64 * 36))
                outgoing.mkdir(parents=True, exist_ok=True)
                for index in range(4):
                    (outgoing / f"{index:08d}.png").write_bytes(fake_png())
                return Result(0, "")

            with patch("cinepulse.rife_benchmark.subprocess.run", side_effect=fake_run):
                sample = run_candidate(
                    executable=root / "rife.exe",
                    model=root / "rife-v4.6",
                    incoming=incoming,
                    outgoing=outgoing,
                    policy=RifePolicy("1:1:1"),
                    uhd=True,
                    ffmpeg="ffmpeg",
                )
            self.assertTrue(sample.accepted)
            self.assertEqual(sample.output_frames, 4)

    def test_machine_black_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "in"
            outgoing = root / "out"
            incoming.mkdir()
            for index in range(2):
                (incoming / f"{index:08d}.png").write_bytes(fake_png())

            def fake_run(command, **_kwargs):
                if "rawvideo" in command:
                    return Result(0, bytes(64 * 36))
                outgoing.mkdir(parents=True, exist_ok=True)
                for index in range(4):
                    (outgoing / f"{index:08d}.png").write_bytes(fake_png())
                return Result(0, "")

            with patch("cinepulse.rife_benchmark.subprocess.run", side_effect=fake_run):
                sample = run_candidate(
                    executable=root / "rife.exe",
                    model=root / "rife-v4.6",
                    incoming=incoming,
                    outgoing=outgoing,
                    policy=RifePolicy("1:1:1"),
                    uhd=True,
                    ffmpeg="ffmpeg",
                )
            self.assertFalse(sample.accepted)
            self.assertFalse(sample.black_frame_ok)

    def test_failed_baseline_stops_before_aggressive_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = RifeTuningStore(root / "rife-tuning.json")
            key = RifeTuningKey("RTX Test", 8192, "999.1", "rife-v4.6", 3840, 2160)
            baseline_policy = RifePolicy("1:1:1")
            aggressive_policy = RifePolicy("1:2:1")
            failed = RifeSample(
                baseline_policy,
                5.0,
                False,
                oom=True,
                output_frames=0,
                expected_frames=16,
                black_frame_ok=False,
            )
            with patch("cinepulse.rife_benchmark.run_candidate", return_value=failed) as run:
                winner, samples = benchmark_and_record(
                    store,
                    key,
                    (baseline_policy, aggressive_policy),
                    executable=Path("rife.exe"),
                    model=Path("rife-v4.6"),
                    incoming=Path("input"),
                    work_dir=root / "work",
                    uhd=True,
                    ffmpeg="ffmpeg",
                )
            self.assertIsNone(winner)
            self.assertEqual((failed,), samples)
            self.assertEqual(1, run.call_count)
            self.assertIsNone(store.lookup(key))

    def test_passing_baseline_allows_candidate_and_records_fastest_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = RifeTuningStore(root / "rife-tuning.json")
            key = RifeTuningKey("RTX Test", 8192, "999.1", "rife-v4.6", 3840, 2160)
            baseline_policy = RifePolicy("1:1:1")
            fast_policy = RifePolicy("1:2:1")
            baseline = RifeSample(
                baseline_policy,
                10.0,
                True,
                output_frames=16,
                expected_frames=16,
                black_frame_ok=True,
            )
            fast = RifeSample(
                fast_policy,
                6.0,
                True,
                output_frames=16,
                expected_frames=16,
                black_frame_ok=True,
            )
            with (
                patch("cinepulse.rife_benchmark.run_candidate", side_effect=(baseline, fast)) as run,
                patch("cinepulse.rife_benchmark.sampled_psnr", return_value=80.0),
            ):
                winner, samples = benchmark_and_record(
                    store,
                    key,
                    (baseline_policy, fast_policy),
                    executable=Path("rife.exe"),
                    model=Path("rife-v4.6"),
                    incoming=Path("input"),
                    work_dir=root / "work",
                    uhd=True,
                    ffmpeg="ffmpeg",
                )
            self.assertEqual(fast_policy, winner)
            self.assertEqual(2, run.call_count)
            self.assertTrue(samples[1].quality_ok)
            self.assertEqual(80.0, samples[1].quality_psnr_db)
            self.assertEqual(fast_policy, store.lookup(key))

    def test_faster_candidate_below_visual_parity_floor_cannot_win(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = RifeTuningStore(root / "rife-tuning.json")
            key = RifeTuningKey("RTX Test", 8192, "999.1", "rife-v4.6", 3840, 2160)
            baseline_policy = RifePolicy("1:1:1")
            fast_policy = RifePolicy("1:2:1")
            baseline = RifeSample(baseline_policy, 10.0, True, output_frames=16, expected_frames=16)
            fast = RifeSample(fast_policy, 4.0, True, output_frames=16, expected_frames=16)
            with (
                patch("cinepulse.rife_benchmark.run_candidate", side_effect=(baseline, fast)),
                patch("cinepulse.rife_benchmark.sampled_psnr", return_value=41.0),
            ):
                winner, samples = benchmark_and_record(
                    store,
                    key,
                    (baseline_policy, fast_policy),
                    executable=Path("rife.exe"),
                    model=Path("rife-v4.6"),
                    incoming=Path("input"),
                    work_dir=root / "work",
                    uhd=True,
                    ffmpeg="ffmpeg",
                )
            self.assertEqual(baseline_policy, winner)
            self.assertFalse(samples[1].quality_ok)
            self.assertFalse(samples[1].accepted)
            self.assertEqual(41.0, samples[1].quality_psnr_db)

    def test_corrupt_faster_candidate_cannot_beat_valid_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = RifeTuningStore(root / "rife-tuning.json")
            key = RifeTuningKey("RTX Test", 8192, "999.1", "rife-v4.6", 3840, 2160)
            baseline_policy = RifePolicy("1:1:1")
            fast_policy = RifePolicy("1:2:1")
            baseline = RifeSample(
                baseline_policy,
                10.0,
                True,
                output_frames=16,
                expected_frames=16,
                black_frame_ok=True,
            )
            corrupt = RifeSample(
                fast_policy,
                4.0,
                True,
                output_frames=15,
                expected_frames=16,
                black_frame_ok=True,
            )
            with patch("cinepulse.rife_benchmark.run_candidate", side_effect=(baseline, corrupt)):
                winner, _samples = benchmark_and_record(
                    store,
                    key,
                    (baseline_policy, fast_policy),
                    executable=Path("rife.exe"),
                    model=Path("rife-v4.6"),
                    incoming=Path("input"),
                    work_dir=root / "work",
                    uhd=True,
                    ffmpeg="ffmpeg",
                )
            self.assertEqual(baseline_policy, winner)
            self.assertEqual(baseline_policy, store.lookup(key))


if __name__ == "__main__":
    unittest.main()
