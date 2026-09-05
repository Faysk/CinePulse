from __future__ import annotations

import unittest

from cinepulse.adaptive_runtime import AdaptiveRuntimeController
from cinepulse.hardware_telemetry import GpuSample, HardwareSample


def sample(*, temp: float = 70.0, power: float = 80.0, limit: float = 140.0, util: float = 90.0) -> HardwareSample:
    return HardwareSample(
        timestamp=1.0,
        monotonic=1.0,
        stage="IA 2/3",
        cpu_total_percent=60.0,
        cpu_per_logical_percent=(),
        ram_total_mb=65536.0,
        ram_used_mb=32000.0,
        ram_available_mb=32000.0,
        ram_percent=50.0,
        disk_read_mbps=20.0,
        disk_write_mbps=30.0,
        gpus=(GpuSample(
            index=0,
            name="RTX Test",
            utilization_percent=util,
            power_w=power,
            power_limit_w=limit,
            temperature_c=temp,
            graphics_clock_mhz=2200.0,
            vram_free_mb=5000.0,
        ),),
    )


class H8AdaptiveIntegrationTests(unittest.TestCase):
    def test_normal_mode_retains_legacy_behavior(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        for _ in range(4):
            decision = controller.observe(sample(power=139.0, limit=140.0, util=70.0))
        self.assertEqual(0, decision.level)
        self.assertEqual(1.0, decision.cpu_scale)
        self.assertTrue(decision.allow_extract_overlap)

    def test_overnight_power_pressure_downshifts_existing_envelope(self) -> None:
        controller = AdaptiveRuntimeController(
            overnight=True,
            overnight_window=2,
            allow_extract_overlap=True,
            allow_pack_overlap=True,
        )
        controller.observe(sample(power=139.0, limit=140.0, util=70.0))
        decision = controller.observe(sample(power=139.0, limit=140.0, util=70.0))
        self.assertEqual(2, decision.level)
        self.assertFalse(decision.allow_extract_overlap)
        self.assertFalse(decision.allow_pack_overlap)
        self.assertLess(decision.cpu_scale, 1.0)
        self.assertLessEqual(decision.limit_cpu_threads(28), 28)

    def test_overnight_critical_heat_surfaces_cooldown_without_system_mutation(self) -> None:
        controller = AdaptiveRuntimeController(overnight=True, overnight_window=2)
        controller.observe(sample(temp=90.0))
        decision = controller.observe(sample(temp=90.0))
        self.assertEqual(2, decision.level)
        self.assertEqual(10.0, decision.cooldown_hint_seconds)
        # H8 critical pressure intentionally keeps 60% of the proven CPU
        # envelope; it is not the H4 50% chunk-scale contract.
        self.assertEqual(17, decision.limit_cpu_threads(28))


if __name__ == "__main__":
    unittest.main()
