from __future__ import annotations

import unittest

from cinepulse.adaptive_runtime import AdaptiveRuntimeController
from cinepulse.hardware_telemetry import GpuSample, HardwareSample


def sample(*, ram: float | None = 40.0, temperature: float | None = 60.0, vram_free: float | None = 6000.0, gpu_index: int = 0) -> HardwareSample:
    return HardwareSample(
        timestamp=1.0, monotonic=1.0, stage="IA 2/3", cpu_total_percent=50.0,
        cpu_per_logical_percent=(), ram_total_mb=65536.0, ram_used_mb=None,
        ram_available_mb=None, ram_percent=ram, disk_read_mbps=100.0, disk_write_mbps=100.0,
        gpus=(GpuSample(index=gpu_index, name="GPU", temperature_c=temperature, vram_free_mb=vram_free),),
    )


class AdaptiveRuntimeControllerTests(unittest.TestCase):
    def test_healthy_sample_preserves_full_envelope(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        decision = controller.observe(sample())
        self.assertEqual(0, decision.level)
        self.assertEqual(1.0, decision.chunk_scale)
        self.assertEqual(1.0, decision.cpu_scale)
        self.assertTrue(decision.allow_extract_overlap)
        self.assertTrue(decision.allow_pack_overlap)

    def test_critical_ram_and_vram_do_not_preemptively_throttle(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        decision = controller.observe(sample(ram=99.9, temperature=99.0, vram_free=1.0))
        self.assertEqual(0, decision.level)
        self.assertEqual(100, decision.limit_chunk_frames(100))
        self.assertEqual(28, decision.limit_cpu_threads(28))
        self.assertTrue(decision.allow_extract_overlap)
        self.assertTrue(decision.allow_pack_overlap)
        self.assertEqual((), decision.reasons)

    def test_missing_telemetry_does_not_change_full_envelope(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        decision = controller.observe(sample(ram=None, vram_free=None))
        self.assertEqual(0, decision.level)
        self.assertEqual(1.0, decision.chunk_scale)
        self.assertTrue(decision.allow_extract_overlap)
        self.assertTrue(decision.allow_pack_overlap)

    def test_overnight_pressure_measurements_do_not_reduce_runtime(self) -> None:
        controller = AdaptiveRuntimeController(
            allow_extract_overlap=True,
            allow_pack_overlap=True,
            overnight=True,
            overnight_window=3,
        )
        controller.record_throughput(100.0)
        controller.record_throughput(10.0)
        controller.record_instability()
        decision = controller.observe(sample(ram=99.0, temperature=99.0, vram_free=1.0))
        self.assertEqual(0, decision.level)
        self.assertEqual(1.0, decision.cpu_scale)
        self.assertEqual(1.0, decision.chunk_scale)
        self.assertTrue(decision.allow_extract_overlap)
        self.assertTrue(decision.allow_pack_overlap)

    def test_minimum_frame_contract_is_still_respected(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True)
        decision = controller.observe(sample(vram_free=1.0))
        self.assertEqual(2, decision.limit_chunk_frames(2, minimum=2))


if __name__ == "__main__":
    unittest.main()
