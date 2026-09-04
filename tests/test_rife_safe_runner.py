from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

from cinepulse.rife_safe_runner import execution_policy, validate_png, validate_png_sequence


def _fake_png(width: int = 64, height: int = 36, *, complete: bool = True) -> bytes:
    # The validator intentionally checks the same structural invariants used by
    # the incident recovery: PNG signature, IHDR dimensions and terminal IEND.
    body = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    if complete:
        body += b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return body


class RifeSafeRunnerTests(unittest.TestCase):
    def test_8k_gpu_policy_forces_uhd_serial_native_2x(self) -> None:
        policy = execution_policy(8, 7680, 4320, 17, "gpu")
        self.assertTrue(policy.uhd)
        self.assertEqual("1:1:1", policy.jobs)
        self.assertEqual(16, policy.native_target)
        self.assertEqual(17, policy.requested_target)

    def test_non_uhd_gpu_keeps_parallel_policy(self) -> None:
        policy = execution_policy(8, 1920, 1080, 16, "gpu")
        self.assertFalse(policy.uhd)
        self.assertEqual("2:2:2", policy.jobs)

    def test_cpu_policy_uses_cpu_safe_jobs(self) -> None:
        policy = execution_policy(8, 7680, 4320, 16, "cpu")
        self.assertEqual("1:2:2", policy.jobs)

    def test_png_validator_accepts_complete_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index in range(3):
                (root / f"{index:08d}.png").write_bytes(_fake_png())
            frames = validate_png_sequence(root, 3)
            self.assertEqual(3, len(frames))
            self.assertEqual((64, 36), validate_png(frames[0]))

    def test_png_validator_rejects_missing_iend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "00000000.png"
            path.write_bytes(_fake_png(complete=False))
            with self.assertRaisesRegex(ValueError, "truncado"):
                validate_png(path)

    def test_png_validator_rejects_mixed_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "00000000.png").write_bytes(_fake_png(64, 36))
            (root / "00000001.png").write_bytes(_fake_png(80, 45))
            with self.assertRaisesRegex(ValueError, "inconsistentes"):
                validate_png_sequence(root, 2)


if __name__ == "__main__":
    unittest.main()
