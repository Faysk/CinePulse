from __future__ import annotations

from pathlib import Path
import unittest

from cinepulse.hardware_telemetry import GpuSample, HardwareSample
from cinepulse.overnight_runtime import OvernightRuntimeController


def sample(*, temp: float = 70.0, gpu_util: float = 90.0, power: float = 80.0, power_limit: float = 140.0, clock: float = 2200.0, ram: float = 60.0, read: float = 20.0, write: float = 30.0) -> HardwareSample:
    gpu = GpuSample(index=0, name="RTX Test", utilization_percent=gpu_util, power_w=power, power_limit_w=power_limit, temperature_c=temp, graphics_clock_mhz=clock)
    return HardwareSample(timestamp=1.0, monotonic=1.0, stage="neural", cpu_total_percent=60.0, cpu_per_logical_percent=(60.0, 60.0), ram_total_mb=64000.0, ram_used_mb=32000.0, ram_available_mb=32000.0, ram_percent=ram, disk_read_mbps=read, disk_write_mbps=write, gpus=(gpu,))


class OvernightRuntimeTests(unittest.TestCase):
    def warmup(self, controller: OvernightRuntimeController, rate: float = 100.0) -> None:
        for _ in range(controller.window):
            controller.record_throughput(rate)
            controller.observe(sample())

    def test_healthy_window_keeps_benchmark_proven_envelope(self) -> None:
        controller = OvernightRuntimeController(window=3, baseline_overlap_depth=3, scratch_sustainable_mbps=500)
        self.warmup(controller)
        decision = controller.observe(sample())
        self.assertEqual(0, decision.pressure_level)
        self.assertEqual(3, decision.overlap_depth)

    def test_sustained_heat_without_throughput_loss_does_not_downshift(self) -> None:
        controller = OvernightRuntimeController(window=2, baseline_overlap_depth=3)
        self.warmup(controller)
        for _ in range(4):
            controller.record_throughput(103.0)
            decision = controller.observe(sample(temp=92.0))
        self.assertEqual(0, decision.pressure_level)
        self.assertEqual(3, decision.overlap_depth)

    def test_heat_plus_measured_throughput_regression_downshifts(self) -> None:
        controller = OvernightRuntimeController(window=2, baseline_overlap_depth=3)
        self.warmup(controller)
        for _ in range(2):
            controller.record_throughput(86.0)
            decision = controller.observe(sample(temp=87.0))
        self.assertEqual(2, decision.pressure_level)
        self.assertEqual(1, decision.overlap_depth)
        self.assertTrue(any("throughput" in reason for reason in decision.reasons))

    def test_power_limit_alone_does_not_downshift_when_throughput_holds(self) -> None:
        controller = OvernightRuntimeController(window=2)
        self.warmup(controller)
        for _ in range(2):
            controller.record_throughput(101.0)
            decision = controller.observe(sample(gpu_util=70.0, power=138.0, power_limit=140.0))
        self.assertEqual(0, decision.pressure_level)

    def test_power_pressure_with_real_throughput_loss_reduces_upstream_pressure(self) -> None:
        controller = OvernightRuntimeController(window=2)
        self.warmup(controller)
        for _ in range(2):
            controller.record_throughput(90.0)
            decision = controller.observe(sample(gpu_util=70.0, power=138.0, power_limit=140.0))
        self.assertGreaterEqual(decision.pressure_level, 2)
        self.assertTrue(any("potência" in reason for reason in decision.reasons))

    def test_scratch_saturation_reduces_overlap_directly(self) -> None:
        controller = OvernightRuntimeController(window=2, scratch_sustainable_mbps=100.0)
        controller.observe(sample(read=45.0, write=50.0))
        decision = controller.observe(sample(read=45.0, write=50.0))
        self.assertEqual(2, decision.pressure_level)
        self.assertEqual(1, decision.overlap_depth)

    def test_reported_instability_is_direct_safety_signal(self) -> None:
        controller = OvernightRuntimeController(window=2)
        controller.record_instability()
        controller.observe(sample(temp=60.0))
        decision = controller.observe(sample(temp=60.0))
        self.assertEqual(3, decision.pressure_level)
        self.assertEqual(10.0, decision.cooldown_hint_seconds)

    def test_decisions_are_monotonic_inside_one_render(self) -> None:
        controller = OvernightRuntimeController(window=2, scratch_sustainable_mbps=100.0)
        controller.observe(sample(read=50.0, write=50.0))
        hot = controller.observe(sample(read=50.0, write=50.0))
        for _ in range(4):
            cool = controller.observe(sample(read=0.0, write=0.0))
        self.assertEqual(hot.pressure_level, cool.pressure_level)

    def test_h8_control_plane_cannot_mutate_global_machine_policy(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "cinepulse"
        control_plane = "\n".join((root / name).read_text(encoding="utf-8").lower() for name in ("overnight_runtime.py", "adaptive_runtime.py"))
        for token in ("import subprocess", "from subprocess", "powercfg", "realtime_priority_class", "priority_realtime", "nvidia-settings", "nvidia-smi -pl", "nvidia-smi --power-limit"):
            self.assertNotIn(token, control_plane, token)


if __name__ == "__main__":
    unittest.main()
