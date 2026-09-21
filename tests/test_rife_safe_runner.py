from __future__ import annotations

import io
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cinepulse.rife_safe_runner import (
    _hardware_tuning_policy,
    _limit_policy_by_live_vram,
    _run_native_with_rollback,
    RifeExecutionPolicy,
    execution_policy,
    main,
    run_safe_rife,
    validate_png,
    validate_png_sequence,
)
from cinepulse.hardware import HardwareProfile
from cinepulse.rife_tuning import RifePolicy


def _fake_png(width: int = 64, height: int = 36, *, complete: bool = True) -> bytes:
    body = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    if complete:
        body += b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
    return body


class RifeSafeRunnerTests(unittest.TestCase):
    def test_execution_policy_keeps_legacy_default_for_direct_callers(self) -> None:
        uhd = execution_policy(8, 7680, 4320, 17, "gpu")
        hd = execution_policy(8, 1920, 1080, 16, "gpu")
        self.assertEqual("1:1:1", uhd.jobs)
        self.assertEqual("2:2:2", hd.jobs)

    def test_full_selector_ignores_missing_live_vram(self) -> None:
        selected, measured, reason = _limit_policy_by_live_vram(
            None, uhd=False, free_vram_mb=None, gpu_index=0
        )
        self.assertEqual(selected, RifePolicy("3:3:3", 0))
        self.assertFalse(measured)
        self.assertIn("full-utilization", reason)

    def test_full_selector_ignores_low_live_vram(self) -> None:
        selected, measured, reason = _limit_policy_by_live_vram(
            None, uhd=False, free_vram_mb=1.0, gpu_index=0
        )
        self.assertEqual(selected, RifePolicy("3:3:3", 0))
        self.assertFalse(measured)
        self.assertIn("ignored", reason)

    def test_uhd_full_selector_starts_parallel_without_live_probe(self) -> None:
        selected, measured, _ = _limit_policy_by_live_vram(
            None, uhd=True, free_vram_mb=1.0, gpu_index=2
        )
        self.assertEqual(selected, RifePolicy("2:2:2", 2))
        self.assertFalse(measured)

    def test_existing_tuned_policy_is_not_live_vram_gated(self) -> None:
        tuned = RifePolicy("3:3:3", 1)
        selected, measured, reason = _limit_policy_by_live_vram(
            tuned, uhd=False, free_vram_mb=1.0, gpu_index=1
        )
        self.assertEqual(selected, tuned)
        self.assertTrue(measured)
        self.assertIn("without live VRAM gating", reason)

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

    def test_oom_retries_fixed_conservative_fallback_without_live_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            native_dir = Path(temporary) / "native"
            aggressive = RifeExecutionPolicy(
                uhd=False,
                jobs="3:3:3",
                native_target=8,
                requested_target=8,
                gpu_index=0,
                measured=False,
            )
            fallback = RifeExecutionPolicy(
                uhd=False,
                jobs="2:2:2",
                native_target=8,
                requested_target=8,
                gpu_index=0,
                measured=False,
            )
            calls = {"count": 0}

            def fake_run(_command, *, cwd=None):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("VK_ERROR_OUT_OF_DEVICE_MEMORY")

            with (
                patch("cinepulse.rife_safe_runner._run", side_effect=fake_run),
                patch("cinepulse.rife_safe_runner.validate_png_sequence", return_value=[]),
            ):
                applied = _run_native_with_rollback(
                    rife_executable=Path("rife-ncnn-vulkan.exe"),
                    model=Path("rife-v4.6"),
                    incoming=Path("incoming"),
                    native_dir=native_dir,
                    policy=aggressive,
                    fallback=fallback,
                    tuning_key=None,
                    tuning_store=None,
                )

            self.assertEqual("2:2:2", applied.jobs)
            self.assertEqual(2, calls["count"])

    def test_repeated_oom_walks_fallback_to_serial_without_live_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            native_dir = Path(temporary) / "native"
            aggressive = RifeExecutionPolicy(
                uhd=False,
                jobs="3:3:3",
                native_target=8,
                requested_target=8,
                gpu_index=0,
                measured=False,
            )
            fallback = RifeExecutionPolicy(
                uhd=False,
                jobs="2:2:2",
                native_target=8,
                requested_target=8,
                gpu_index=0,
                measured=False,
            )
            calls: list[str] = []

            def fake_run(command, *, cwd=None):
                jobs = command[command.index("-j") + 1]
                calls.append(jobs)
                if len(calls) <= 2:
                    raise RuntimeError("VK_ERROR_OUT_OF_DEVICE_MEMORY")

            with (
                patch("cinepulse.rife_safe_runner._run", side_effect=fake_run),
                patch("cinepulse.rife_safe_runner.validate_png_sequence", return_value=[]),
            ):
                applied = _run_native_with_rollback(
                    rife_executable=Path("rife-ncnn-vulkan.exe"),
                    model=Path("rife-v4.6"),
                    incoming=Path("incoming"),
                    native_dir=native_dir,
                    policy=aggressive,
                    fallback=fallback,
                    tuning_key=None,
                    tuning_store=None,
                )

            self.assertEqual(["3:3:3", "2:2:2", "1:1:1"], calls)
            self.assertEqual("1:1:1", applied.jobs)

    def test_session_override_becomes_rollback_floor_without_upshift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "in"
            incoming.mkdir()
            outgoing = root / "out"
            captured = {}

            def fake_rollback(**kwargs):
                captured["policy"] = kwargs["policy"]
                captured["fallback"] = kwargs["fallback"]
                return kwargs["policy"]

            with (
                patch(
                    "cinepulse.rife_safe_runner.validate_png_sequence",
                    return_value=[Path("00000000.png"), Path("00000001.png")],
                ),
                patch("cinepulse.rife_safe_runner.validate_png", return_value=(1920, 1080)),
                patch(
                    "cinepulse.rife_safe_runner.detect_hardware",
                    return_value=HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 0),
                ),
                patch("cinepulse.rife_safe_runner._run_native_with_rollback", side_effect=fake_rollback),
                patch("cinepulse.rife_safe_runner._move_native_frames"),
                patch("cinepulse.rife_safe_runner._promote_atomic_output"),
            ):
                applied = run_safe_rife(
                    rife_executable=root / "rife.exe",
                    model=root / "rife-v4.6",
                    incoming=incoming,
                    outgoing=outgoing,
                    requested_target=4,
                    device="gpu",
                    jobs_override="1:1:1",
                )

            self.assertEqual("1:1:1", applied.jobs)
            self.assertEqual("1:1:1", captured["policy"].jobs)
            self.assertEqual("1:1:1", captured["fallback"].jobs)

    def test_session_override_cannot_exceed_full_utilization_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "in"
            incoming.mkdir()
            with (
                patch(
                    "cinepulse.rife_safe_runner.validate_png_sequence",
                    return_value=[Path("00000000.png"), Path("00000001.png")],
                ),
                patch("cinepulse.rife_safe_runner.validate_png", return_value=(1920, 1080)),
                patch(
                    "cinepulse.rife_safe_runner.detect_hardware",
                    return_value=HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 0),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "não pode exceder"):
                    run_safe_rife(
                        rife_executable=root / "rife.exe",
                        model=root / "rife-v4.6",
                        incoming=incoming,
                        outgoing=root / "out",
                        requested_target=4,
                        device="gpu",
                        jobs_override="8:8:8",
                    )
                with self.assertRaisesRegex(ValueError, "não pode exceder"):
                    run_safe_rife(
                        rife_executable=root / "rife.exe",
                        model=root / "rife-v4.6",
                        incoming=incoming,
                        outgoing=root / "out2",
                        requested_target=4,
                        device="gpu",
                        jobs_override="8:1:8",
                    )

    def test_cli_reports_applied_policy_for_parent_session_memory(self) -> None:
        applied = RifeExecutionPolicy(
            uhd=False,
            jobs="1:1:1",
            native_target=4,
            requested_target=4,
            gpu_index=2,
            measured=False,
        )
        output = io.StringIO()
        with (
            patch("cinepulse.rife_safe_runner.run_safe_rife", return_value=applied) as run,
            redirect_stdout(output),
        ):
            code = main(
                [
                    "--rife", "rife.exe",
                    "--model", "rife-v4.6",
                    "--input", "in",
                    "--output", "out",
                    "--frames", "4",
                    "--device", "gpu",
                    "--jobs-override", "1:1:1",
                    "--gpu-index", "2",
                ]
            )
        self.assertEqual(0, code)
        self.assertIn("CINEPULSE_RIFE_SAFE APPLIED jobs=1:1:1 gpu=2", output.getvalue())
        self.assertEqual("1:1:1", run.call_args.kwargs["jobs_override"])
        self.assertEqual(2, run.call_args.kwargs["gpu_index"])

    def test_pinned_gpu_index_skips_adapter_rediscovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "in"
            incoming.mkdir()
            outgoing = root / "out"

            def fake_rollback(**kwargs):
                return kwargs["policy"]

            with (
                patch(
                    "cinepulse.rife_safe_runner.validate_png_sequence",
                    return_value=[Path("00000000.png"), Path("00000001.png")],
                ),
                patch("cinepulse.rife_safe_runner.validate_png", return_value=(1920, 1080)),
                patch(
                    "cinepulse.rife_safe_runner.detect_hardware",
                    side_effect=AssertionError("pinned GPU must not rediscover adapters"),
                ),
                patch("cinepulse.rife_safe_runner._run_native_with_rollback", side_effect=fake_rollback),
                patch("cinepulse.rife_safe_runner._move_native_frames"),
                patch("cinepulse.rife_safe_runner._promote_atomic_output"),
            ):
                applied = run_safe_rife(
                    rife_executable=root / "rife.exe",
                    model=root / "rife-v4.6",
                    incoming=incoming,
                    outgoing=outgoing,
                    requested_target=4,
                    device="gpu",
                    gpu_index=2,
                )

            self.assertEqual(2, applied.gpu_index)

    def test_direct_native_publish_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "in"
            incoming.mkdir()
            for index in range(2):
                (incoming / f"{index:08d}.png").write_bytes(_fake_png())
            outgoing = root / "out"
            applied = RifeExecutionPolicy(
                uhd=False,
                jobs="3:3:3",
                native_target=4,
                requested_target=4,
                gpu_index=0,
                measured=False,
            )

            def fake_rollback(**kwargs):
                native_dir = kwargs["native_dir"]
                for index in range(4):
                    (native_dir / f"{index:08d}.png").write_bytes(_fake_png())
                return applied

            with (
                patch(
                    "cinepulse.rife_safe_runner.detect_hardware",
                    return_value=HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 0),
                ),
                patch("cinepulse.rife_safe_runner._run_native_with_rollback", side_effect=fake_rollback),
            ):
                result = run_safe_rife(
                    rife_executable=root / "rife.exe",
                    model=root / "rife-v4.6",
                    incoming=incoming,
                    outgoing=outgoing,
                    requested_target=4,
                    device="gpu",
                )

            self.assertEqual(applied, result)
            self.assertEqual(4, len(list(outgoing.glob("*.png"))))
            self.assertEqual([], list(root.glob(".out.publish-*")))
            self.assertEqual([], list(root.glob(".out.native-*")))

    def test_native_publish_failure_never_leaves_partial_official_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "in"
            incoming.mkdir()
            for index in range(2):
                (incoming / f"{index:08d}.png").write_bytes(_fake_png())
            outgoing = root / "out"
            applied = RifeExecutionPolicy(
                uhd=False,
                jobs="3:3:3",
                native_target=4,
                requested_target=4,
                gpu_index=0,
                measured=False,
            )

            def fake_rollback(**kwargs):
                native_dir = kwargs["native_dir"]
                for index in range(4):
                    (native_dir / f"{index:08d}.png").write_bytes(_fake_png())
                return applied

            def fail_publish(_native_dir, publish_dir, _expected):
                publish_dir.mkdir(parents=False, exist_ok=False)
                (publish_dir / "00000001.png").write_bytes(_fake_png())
                raise OSError("simulated publish failure")

            with (
                patch(
                    "cinepulse.rife_safe_runner.detect_hardware",
                    return_value=HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 0),
                ),
                patch("cinepulse.rife_safe_runner._run_native_with_rollback", side_effect=fake_rollback),
                patch("cinepulse.rife_safe_runner._move_native_frames", side_effect=fail_publish),
            ):
                with self.assertRaisesRegex(OSError, "simulated publish failure"):
                    run_safe_rife(
                        rife_executable=root / "rife.exe",
                        model=root / "rife-v4.6",
                        incoming=incoming,
                        outgoing=outgoing,
                        requested_target=4,
                        device="gpu",
                    )

            self.assertFalse(outgoing.exists())
            self.assertEqual([], list(root.glob(".out.publish-*")))
            self.assertEqual([], list(root.glob(".out.native-*")))

    def test_retime_failure_never_leaves_partial_official_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            incoming = root / "in"
            incoming.mkdir()
            for index in range(2):
                (incoming / f"{index:08d}.png").write_bytes(_fake_png())
            outgoing = root / "out"
            applied = RifeExecutionPolicy(
                uhd=False,
                jobs="3:3:3",
                native_target=4,
                requested_target=3,
                gpu_index=0,
                measured=False,
            )

            def fake_rollback(**kwargs):
                native_dir = kwargs["native_dir"]
                for index in range(4):
                    (native_dir / f"{index:08d}.png").write_bytes(_fake_png())
                return applied

            def fail_retime(command, *, cwd=None):
                target = Path(command[-1]).parent
                (target / "00000001.png").write_bytes(_fake_png())
                raise RuntimeError("simulated retime failure")

            with (
                patch(
                    "cinepulse.rife_safe_runner.detect_hardware",
                    return_value=HardwareProfile("CPU Test", 28, "RTX Test", 8192, "999.1", 0),
                ),
                patch("cinepulse.rife_safe_runner._run_native_with_rollback", side_effect=fake_rollback),
                patch("cinepulse.rife_safe_runner._find_ffmpeg", return_value="ffmpeg"),
                patch("cinepulse.rife_safe_runner._run", side_effect=fail_retime),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated retime failure"):
                    run_safe_rife(
                        rife_executable=root / "rife.exe",
                        model=root / "rife-v4.6",
                        incoming=incoming,
                        outgoing=outgoing,
                        requested_target=3,
                        device="gpu",
                    )

            self.assertFalse(outgoing.exists())
            self.assertEqual([], list(root.glob(".out.publish-*")))
            self.assertEqual([], list(root.glob(".out.native-*")))

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
