from __future__ import annotations

import unittest

from scripts.overnight_acceptance import analyze


def telemetry(*, wall=3600.0, temp=78.0, status="success", sample_count=1800):
    return {
        "status": status,
        "sample_interval_seconds": 2.0,
        "stage_events": [{"stage": "IA 2/3", "detail": "Lote 1: Real-ESRGAN em 120 quadro(s)."}],
        "summary": {
            "wall_seconds": wall,
            "stages": {"IA 2/3": {"wall_seconds": 20.0}},
            "overall": {
                "sample_count": sample_count,
                "gpu": {"peak_temperature_c": temp, "minimum_vram_free_mb": 1024.0},
                "ram": {"peak_percent": 75.0},
                "disk": {"average_write_mbps": 300.0, "peak_write_mbps": 500.0},
            },
        },
    }


class OvernightAcceptanceTests(unittest.TestCase):
    def test_sustained_candidate_can_pass_against_baseline(self) -> None:
        result = analyze(telemetry(wall=3600), baseline_telemetry=telemetry(wall=3900), scenario="1080p30_to_4k60", minimum_seconds=1800, quality_passed=True)
        self.assertTrue(result["passed"])
        self.assertGreater(result["evidence"]["sustained_speedup_vs_baseline"], 1.0)
        self.assertEqual(6.0, result["evidence"]["throughput"]["stages"]["IA 2/3"]["units_per_second"])

    def test_hot_but_faster_stable_run_is_not_rejected_for_temperature(self) -> None:
        result = analyze(telemetry(wall=3500, temp=94.0), baseline_telemetry=telemetry(wall=3900), scenario="1080p30_to_4k60", minimum_seconds=1800, quality_passed=True)
        self.assertTrue(result["passed"])
        self.assertTrue(result["checks"]["gpu_temperature_observed"])
        self.assertTrue(any("temperature alone" in note for note in result["notes"]))

    def test_missing_quality_gate_rejects(self) -> None:
        result = analyze(telemetry(), baseline_telemetry=telemetry(wall=3900), scenario="720p24_to_8k120_music", minimum_seconds=1800, quality_passed=False)
        self.assertFalse(result["passed"])

    def test_sustained_throughput_regression_rejects_even_when_cool(self) -> None:
        result = analyze(telemetry(wall=4200, temp=65.0, sample_count=2100), baseline_telemetry=telemetry(wall=3600), scenario="1080p30_to_4k60", minimum_seconds=1800, quality_passed=True)
        self.assertFalse(result["checks"]["sustained_throughput_not_worse"])
        self.assertFalse(result["passed"])

    def test_missing_baseline_rejects_physical_acceptance(self) -> None:
        result = analyze(telemetry(), baseline_telemetry=None, scenario="1080p30_to_4k60", minimum_seconds=1800, quality_passed=True)
        self.assertFalse(result["checks"]["baseline_present"])
        self.assertFalse(result["passed"])

    def test_sparse_telemetry_rejects(self) -> None:
        result = analyze(telemetry(sample_count=10), baseline_telemetry=telemetry(wall=3900), scenario="1080p30_to_4k60", minimum_seconds=1800, quality_passed=True)
        self.assertFalse(result["checks"]["telemetry_coverage"])


if __name__ == "__main__":
    unittest.main()
