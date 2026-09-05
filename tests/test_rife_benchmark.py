from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.rife_benchmark import looks_like_oom, run_candidate
from cinepulse.rife_tuning import RifePolicy


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
                    requested_frames=4,
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
                    requested_frames=4,
                    uhd=True,
                    ffmpeg="ffmpeg",
                )
            self.assertFalse(sample.accepted)
            self.assertFalse(sample.black_frame_ok)


if __name__ == "__main__":
    unittest.main()
