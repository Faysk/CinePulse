from __future__ import annotations

import unittest

from cinepulse.adaptive_runtime import AdaptiveRuntimeController
from cinepulse.hardware_telemetry import GpuSample, HardwareSample


def sample(*, ram: float | None = 40.0, temperature: float | None = 60.0, vram_free: float | None = 6000.0, gpu_index: int = 0) -> HardwareSample:
    return HardwareSample(
        timestamp=1.0,
        monotonic=1.0,
        stage="IA 2/3",
        cpu_total_percent=50.0,
        cpu_per_logical_percent=(),
        ram_total_mb=65536.0,
        ram_used_mb=None,
        ram_available_mb=None,
        ram_percent=ram,
        disk_read_mbps=100.0,
        disk_write_mbps=100.0,
        gpus=(
            GpuSample(
                index=gpu_index,
                name="GPU",
                temperature_c=temperature,
                vram_free_mb=vram_free,
            ),
        ),
    )


class AdaptiveRuntimeControllerTests(unittest.TestCase):
    def test_healthy_sample_preserves_h4_envelope(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        decision = controller.observe(sample())
        self.assertEqual(decision.level, 0)
        self.assertEqual(decision.chunk_scale, 1.0)
        self.assertTrue(decision.allow_extract_overlap)
        self.assertTrue(decision.allow_pack_overlap)
        self.assertEqual(decision.limit_chunk_frames(100), 100)

    def test_caution_pressure_disables_overlap_and_reduces_future_chunks(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        decision = controller.observe(sample(temperature=85.0))
        self.assertEqual(decision.level, 1)
        self.assertFalse(decision.allow_extract_overlap)
        self.assertFalse(decision.allow_pack_overlap)
        self.assertEqual(decision.limit_chunk_frames(100), 75)
        self.assertIn("GPU 85.0°C", decision.reasons)

    def test_critical_pressure_halves_future_chunk_limit(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        decision = controller.observe(sample(ram=95.0, temperature=89.0, vram_free=300.0))
        self.assertEqual(decision.level, 2)
        self.assertEqual(decision.limit_chunk_frames(100), 50)
        self.assertFalse(decision.allow_extract_overlap)
        self.assertFalse(decision.allow_pack_overlap)

    def test_controller_never_ramps_back_up_during_same_render(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True, allow_pack_overlap=True)
        self.assertEqual(controller.observe(sample(temperature=85.0)).level, 1)
        healthy = controller.observe(sample(temperature=60.0, ram=30.0, vram_free=7000.0))
        self.assertEqual(healthy.level, 1)
        self.assertFalse(healthy.allow_extract_overlap)
        self.assertEqual(healthy.chunk_scale, 0.75)

    def test_unknown_sample_never_expands_beyond_h4_baseline(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=False, allow_pack_overlap=False)
        decision = controller.observe(None)
        self.assertFalse(decision.allow_extract_overlap)
        self.assertFalse(decision.allow_pack_overlap)
        self.assertEqual(decision.chunk_scale, 1.0)

    def test_configured_gpu_is_used_for_pressure_evidence(self) -> None:
        controller = AdaptiveRuntimeController(gpu_index=1, allow_extract_overlap=True, allow_pack_overlap=True)
        payload = HardwareSample(
            timestamp=1.0,
            monotonic=1.0,
            stage="RIFE 2/3",
            cpu_total_percent=20.0,
            cpu_per_logical_percent=(),
            ram_total_mb=65536.0,
            ram_used_mb=None,
            ram_available_mb=None,
            ram_percent=40.0,
            disk_read_mbps=None,
            disk_write_mbps=None,
            gpus=(
                GpuSample(index=0, name="GPU0", temperature_c=90.0, vram_free_mb=100.0),
                GpuSample(index=1, name="GPU1", temperature_c=65.0, vram_free_mb=5000.0),
            ),
        )
        self.assertEqual(controller.observe(payload).level, 0)

    def test_rife_minimum_can_be_kept_at_two_frames(self) -> None:
        controller = AdaptiveRuntimeController(allow_extract_overlap=True)
        decision = controller.observe(sample(temperature=90.0))
        self.assertEqual(decision.limit_chunk_frames(2, minimum=2), 2)


if __name__ == "__main__":
    unittest.main()
