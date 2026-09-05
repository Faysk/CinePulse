from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.realesrgan_benchmark import looks_like_oom, png_dimensions, run_candidate
from cinepulse.realesrgan_tuning import RealEsrganPolicy


def write_png_header(path: Path, width: int, height: int) -> None:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )


class _Result:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout


class RealEsrganBenchmarkTests(unittest.TestCase):
    def test_png_dimensions_reads_ihdr_without_pillow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "frame.png"
            write_png_header(path, 320, 180)
            self.assertEqual(png_dimensions(path), (320, 180))

    def test_oom_detection_is_case_insensitive(self) -> None:
        self.assertTrue(looks_like_oom("VK_ERROR_OUT_OF_DEVICE_MEMORY"))
        self.assertTrue(looks_like_oom("failed to allocate buffer"))
        self.assertFalse(looks_like_oom("completed successfully"))

    def test_candidate_requires_exact_frame_count_and_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "in"
            outgoing = root / "out"
            incoming.mkdir()
            for index in range(2):
                write_png_header(incoming / f"frame{index:08d}.png", 100, 50)

            def fake_run(*_args, **_kwargs):
                outgoing.mkdir(parents=True, exist_ok=True)
                for index in range(2):
                    write_png_header(outgoing / f"frame{index:08d}.png", 200, 100)
                return _Result()

            with patch("cinepulse.realesrgan_benchmark.subprocess.run", side_effect=fake_run):
                sample = run_candidate(
                    root / "realesrgan.exe",
                    root / "models",
                    incoming,
                    outgoing,
                    policy=RealEsrganPolicy(),
                    model="realesr-animevideov3",
                    scale=2,
                    expected_frames=2,
                    expected_size=(100, 50),
                )
            self.assertTrue(sample.accepted)

    def test_wrong_output_dimensions_fail_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "in"
            outgoing = root / "out"
            incoming.mkdir()
            write_png_header(incoming / "frame00000000.png", 100, 50)

            def fake_run(*_args, **_kwargs):
                outgoing.mkdir(parents=True, exist_ok=True)
                write_png_header(outgoing / "frame00000000.png", 199, 100)
                return _Result()

            with patch("cinepulse.realesrgan_benchmark.subprocess.run", side_effect=fake_run):
                sample = run_candidate(
                    root / "realesrgan.exe",
                    root / "models",
                    incoming,
                    outgoing,
                    policy=RealEsrganPolicy(),
                    model="realesr-animevideov3",
                    scale=2,
                    expected_frames=1,
                    expected_size=(100, 50),
                )
            self.assertFalse(sample.accepted)

    def test_failed_process_marks_oom_and_rejects_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "in"
            outgoing = root / "out"
            incoming.mkdir()
            write_png_header(incoming / "frame.png", 10, 10)
            with patch(
                "cinepulse.realesrgan_benchmark.subprocess.run",
                return_value=_Result(1, "VK_ERROR_OUT_OF_DEVICE_MEMORY"),
            ):
                sample = run_candidate(
                    root / "realesrgan.exe",
                    root / "models",
                    incoming,
                    outgoing,
                    policy=RealEsrganPolicy(),
                    model="realesr-animevideov3",
                    scale=2,
                    expected_frames=1,
                    expected_size=(10, 10),
                )
            self.assertTrue(sample.oom)
            self.assertFalse(sample.accepted)


if __name__ == "__main__":
    unittest.main()
