from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cinepulse.rife_safe_runner import (
    _hardware_tuning_policy,
    _limit_policy_by_live_vram,
    execution_policy,
    validate_png,
    validate_png_sequence,
)
from cinepulse.hardware import HardwareProfile
from cinepulse.rife_tuning import RifePolicy


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

    def test_tuned_policy_is_suppressed_when_live_vram_is_unknown(self) -> None:
        tuned = RifePolicy("3:3:3", 0)
        selected, measured, reason = _limit_policy_by_live_vram(
            tuned, uhd=False, free_vram_mb=None, gpu_index=0
        )
        self.assertEqual(selected, RifePolicy("2:2:2", 0))
        self.assertFalse(measured)
        self.assertIn("unavailable", reason)

    def test_low_live_vram_forces_serial_policy(self) -> None:
        tuned = RifePolicy("3:3:3", 0)
        selected, measured, _reason = _limit_policy_by_live_vram(
            tuned, uhd=False, free_vram_mb=2500, gpu_index=0
        )
        self.assertEqual(selected, RifePolicy("1:1:1", 0))
        self.assertFalse(measured)

    def test_three_process_tuning_requires_live_headroom(self) -> None:
        tuned = RifePolicy("3:3:3", 0)
        limited, measured_limited, _ = _limit_policy_by_live_vram(
            tuned, uhd=False, free_vram_mb=6000, gpu_index=0
        )
        admitted, measured_admitted, _ = _limit_policy_by_live_vram(
            tuned, uhd=False, free_vram_mb=7000, gpu_index=0
        )
        self.assertEqual(limited, RifePolicy("2:2:2", 0))
        self.assertFalse(measured_limited)
        self.assertEqual(admitted, tuned)
        self.assertTrue(measured_admitted)

    def test_tuning_lookup_reuses_already_detected_hardware_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "rife-v4.6"
            model.mkdir()
            exe = root / "rife-ncnn-vulkan.exe"
            exe.write_bytes(b"exe")
            hardware = HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 1)
            with (
                patch(
                    "cinepulse.rife_safe_runner.bootstrap_component_fingerprint",
                    return_value="rife:v1:" + "a" * 64,
                ),
                patch(
                    "cinepulse.rife_safe_runner.detect_hardware",
                    side_effect=AssertionError("unexpected second hardware probe"),
                ),
            ):
                policy, key, store = _hardware_tuning_policy(
                    1920, 1080, model, exe, hardware
                )
            self.assertIsNone(policy)
            self.assertIsNotNone(key)
            self.assertIsNotNone(store)
            self.assertEqual(1, key.gpu_index)
            self.assertEqual("RTX Test", key.gpu_name)

    def test_precomputed_component_fingerprint_skips_rehash_in_tuning_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "rife-v4.6"
            model.mkdir()
            exe = root / "rife-ncnn-vulkan.exe"
            exe.write_bytes(b"exe")
            hardware = HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 0)
            fingerprint = "rife:v1:" + "a" * 64
            with patch(
                "cinepulse.rife_safe_runner.bootstrap_component_fingerprint",
                side_effect=AssertionError("unexpected component rehash"),
            ):
                policy, key, store = _hardware_tuning_policy(
                    1920,
                    1080,
                    model,
                    exe,
                    hardware,
                    component_fingerprint=fingerprint,
                )
            self.assertIsNone(policy)
            self.assertEqual(fingerprint, key.component_fingerprint)
            self.assertIsNotNone(store)

    def test_hardware_snapshot_exposes_live_vram_without_second_probe(self) -> None:
        hardware = HardwareProfile(
            "CPU Test", 28, "RTX Test", 8192, "999.1", 1, 7000
        )
        self.assertEqual(hardware.gpu_index, 1)
        self.assertEqual(hardware.vram_free_mb, 7000)
        with patch(
            "cinepulse.rife_safe_runner.vram_free_mb",
            side_effect=AssertionError("unexpected initial VRAM re-probe"),
        ):
            selected, measured, reason = _limit_policy_by_live_vram(
                RifePolicy("3:3:3", 1),
                uhd=False,
                free_vram_mb=float(hardware.vram_free_mb),
                gpu_index=hardware.gpu_index,
            )
        self.assertEqual(selected, RifePolicy("3:3:3", 1))
        self.assertTrue(measured)
        self.assertIn("live VRAM", reason)

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
