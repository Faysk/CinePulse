from __future__ import annotations

import unittest

from cinepulse.hardware_advisor import analyze_hardware_summary, analyze_stage


def group(*, samples=5, gpu=None, cpu=None, ram=None, vram_free=None, temp=None, read=0.0, write=0.0):
    return {
        "sample_count": samples,
        "cpu": {"average_percent": cpu},
        "ram": {"peak_percent": ram},
        "disk": {"average_read_mbps": read, "average_write_mbps": write},
        "gpu": {
            "average_utilization_percent": gpu,
            "minimum_vram_free_mb": vram_free,
            "peak_temperature_c": temp,
        },
    }


class HardwareAdvisorTests(unittest.TestCase):
    def test_neural_gpu_starvation_is_detected_conservatively(self) -> None:
        advice = analyze_stage("IA 2/3", group(gpu=41, cpu=52, ram=60, vram_free=2100, temp=70))
        self.assertEqual(advice.bottleneck, "gpu-starved")
        self.assertTrue(advice.gpu_expected)
        self.assertIn("Benchmarke", advice.action)

    def test_cpu_only_stage_is_not_called_gpu_starved(self) -> None:
        advice = analyze_stage("VFX dinâmicos", group(gpu=12, cpu=54, ram=60, vram_free=2500, temp=68))
        self.assertEqual(advice.bottleneck, "balanced")
        self.assertFalse(advice.gpu_expected)

    def test_io_suspected_requires_gpu_expected_and_meaningful_io(self) -> None:
        advice = analyze_stage("RIFE 2/3", group(gpu=35, cpu=44, ram=55, vram_free=1800, temp=65, read=130, write=90))
        self.assertEqual(advice.bottleneck, "io-suspected")

    def test_heat_alone_is_observational_and_does_not_force_downshift_advice(self) -> None:
        advice = analyze_stage("IA 2/3", group(gpu=40, cpu=40, ram=50, vram_free=2200, temp=92))
        self.assertEqual(advice.bottleneck, "gpu-starved")
        self.assertNotIn("Reduza concorrência", advice.action)
        self.assertIn("não reduza carga", advice.reason)
        self.assertIn("92.0", advice.reason)

    def test_hot_saturated_gpu_remains_positive_without_throughput_regression_evidence(self) -> None:
        advice = analyze_stage("Real-ESRGAN", group(gpu=96, cpu=60, ram=62, vram_free=1400, temp=93))
        self.assertEqual(advice.bottleneck, "gpu-saturated")
        self.assertEqual(advice.severity, "ok")
        self.assertIn("não reduza carga", advice.reason)

    def test_memory_pressure_wins_before_starvation(self) -> None:
        advice = analyze_stage("IA 2/3", group(gpu=40, cpu=40, ram=95, vram_free=200, temp=92))
        self.assertEqual(advice.bottleneck, "memory-pressure")
        self.assertIn("Diminua", advice.action)

    def test_cpu_bound_stage_is_reported(self) -> None:
        advice = analyze_stage("Preparando master", group(gpu=45, cpu=94, ram=60, vram_free=2000, temp=70))
        self.assertEqual(advice.bottleneck, "cpu-bound")

    def test_gpu_saturation_is_positive_signal(self) -> None:
        advice = analyze_stage("Real-ESRGAN", group(gpu=96, cpu=60, ram=62, vram_free=1400, temp=78))
        self.assertEqual(advice.bottleneck, "gpu-saturated")
        self.assertEqual(advice.severity, "ok")

    def test_short_stage_fails_closed_as_unknown(self) -> None:
        advice = analyze_stage("IA 2/3", group(samples=1, gpu=20, cpu=20))
        self.assertEqual(advice.bottleneck, "unknown")

    def test_summary_rolls_up_constraints_without_claiming_temperature_is_constraint(self) -> None:
        summary = {
            "stages": {
                "IA 2/3": group(gpu=45, cpu=50, ram=50, vram_free=1800, temp=92),
                "Master": group(gpu=20, cpu=96, ram=50, vram_free=1800, temp=70),
                "RIFE 2/3": group(gpu=80, cpu=60, ram=94, vram_free=900, temp=70),
            }
        }
        advice = analyze_hardware_summary(summary)
        self.assertIn("IA 2/3", advice.gpu_starved_stages)
        self.assertIn("Master", advice.cpu_bound_stages)
        self.assertTrue(advice.memory_constrained)
        self.assertFalse(advice.thermal_constrained)
        self.assertEqual(advice.physical_acceptance, "pending")
        self.assertTrue(advice.needs_attention)


if __name__ == "__main__":
    unittest.main()
