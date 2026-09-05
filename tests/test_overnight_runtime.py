from __future__ import annotations

from pathlib import Path
import unittest

from cinepulse.hardware_telemetry import GpuSample, HardwareSample
from cinepulse.overnight_runtime import OvernightRuntimeController


def sample(
    *,
    temp: float = 70.0,
    gpu_util: float = 90.0,
    power: float = 80.0,
    power_limit: float = 140.0,
    clock: float = 2200.0,
    ram: float = 60.0,
    read: float = 20.0,
    write: float = 30.0,
) -> HardwareSample:
    gpu = GpuSample(
        index=0,
        name="RTX Test",
        utilization_percent=gpu_util,
        power_w=power,
        power_limit_w=power_limit,
        temperature_c=temp,
        graphics_clock_mhz=clock,
    )
    return HardwareSample(
        timestamp=1.0,
        monotonic=1.0,
        stage="neural",
        cpu_total_percent=60.0,
        cpu_per_logical_percent=(60.0, 60.0),
        ram_total_mb=64000.0,
        ram_used_mb=32000.0,
        ram_available_mb=32000.0,
        ram_percent=ram,
        disk_read_mbps=read,
        disk_write_mbps=write,
        gpus=(gpu,),
    )


class OvernightRuntimeTests(unittest.TestCase):
    def test_healthy_window_keeps_benchmark_proven_envelope(self) -> None:
        controller = OvernightRuntimeController(window=3, baseline_overlap_depth=3, scratch_sustainable_mbps=500)
        decision = None
        for _ in range(3):
            decision = controller.observe(sample())
        assert decision is not None
        self.assertEqual(0, decision.pressure_level)
        self.assertEqual(3, decision.overlap_depth)
        self.assertEqual(1.0, decision.cpu_scale)

    def test_sustained_heat_downshifts_without_quality_change(self) -> None:
        controller = OvernightRuntimeController(window=3, baseline_overlap_depth=3)
        for _ in range(3):
            decision = controller.observe(sample(temp=86.0))
        self.assertEqual(2, decision.pressure_level)
        self.assertEqual(1, decision.overlap_depth)
        self.assertLess(decision.cpu_scale, 1.0)
        self.assertLess(decision.chunk_scale, 1.0)

    def test_critical_heat_produces_bounded_cooldown_hint(self) -> None:
        controller = OvernightRuntimeController(window=2)
        controller.observe(sample(temp=90.0))
        decision = controller.observe(sample(temp=90.0))
        self.assertEqual(3, decision.pressure_level)
        self.assertEqual(10.0, decision.cooldown_hint_seconds)
        self.assertEqual(1, decision.overlap_depth)

    def test_power_limit_without_useful_saturation_reduces_upstream_pressure(self) -> None:
        controller = OvernightRuntimeController(window=2)
        controller.observe(sample(gpu_util=70.0, power=138.0, power_limit=140.0))
        decision = controller.observe(sample(gpu_util=72.0, power=138.0, power_limit=140.0))
        self.assertGreaterEqual(decision.pressure_level, 2)
        self.assertTrue(any("potência" in reason for reason in decision.reasons))

    def test_scratch_saturation_reduces_overlap(self) -> None:
        controller = OvernightRuntimeController(window=2, scratch_sustainable_mbps=100.0)
        controller.observe(sample(read=45.0, write=50.0))
        decision = controller.observe(sample(read=45.0, write=50.0))
        self.assertEqual(2, decision.pressure_level)
        self.assertEqual(1, decision.overlap_depth)

    def test_decisions_are_monotonic_inside_one_render(self) -> None:
        controller = OvernightRuntimeController(window=2)
        controller.observe(sample(temp=90.0))
        hot = controller.observe(sample(temp=90.0))
        for _ in range(4):
            cool = controller.observe(sample(temp=60.0))
        self.assertEqual(hot.pressure_level, cool.pressure_level)
        self.assertEqual(hot.chunk_scale, cool.chunk_scale)

    def test_limits_never_increase_baseline_resources(self) -> None:
        controller = OvernightRuntimeController(window=2)
        controller.observe(sample(temp=90.0))
        decision = controller.observe(sample(temp=90.0))
        self.assertLessEqual(decision.limit_threads(28), 28)
        self.assertLessEqual(decision.limit_chunk_frames(240), 240)

    def test_h8_control_plane_cannot_mutate_global_machine_policy(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "cinepulse"
        control_plane = "\n".join(
            (root / name).read_text(encoding="utf-8").lower()
            for name in ("overnight_runtime.py", "adaptive_runtime.py")
        )
        # H8 is an observational/downshift-only scheduler.  Keep process launch,
        # OS power plans, Realtime priority and NVIDIA mutation commands out of
        # the control plane so a future throughput tweak cannot silently turn
        # into a machine-wide setting change.
        forbidden = (
            "import subprocess",
            "from subprocess",
            "powercfg",
            "realtime_priority_class",
            "priority_realtime",
            "nvidia-settings",
            "nvidia-smi -pl",
            "nvidia-smi --power-limit",
        )
        for token in forbidden:
            self.assertNotIn(token, control_plane, token)


if __name__ == "__main__":
    unittest.main()
