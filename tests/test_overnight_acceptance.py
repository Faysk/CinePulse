from __future__ import annotations

import unittest

from scripts.overnight_acceptance import analyze


def telemetry(*, wall=3600.0, temp=78.0, status="success", sample_count=1800):
    return {
        "status": status,
        "sample_interval_seconds": 2.0,
        "stage_events": [
            {"stage": "IA 2/3", "detail": "Lote 1: Real-ESRGAN em 120 quadro(s)."},
        ],
        "summary": {
            "wall_seconds": wall,
            "stages": {"IA 2/3": {"wall_seconds": 20.0}},
            "overall": {
                "sample_count": sample_count,
                "gpu": {
                    "peak_temperature_c": temp,
                    "minimum_vram_free_mb": 1024.0,
                },
                "ram": {"peak_percent": 75.0},
                "disk": {"average_write_mbps": 300.0, "peak_write_mbps": 500.0},
            },
        },
    }


class OvernightAcceptanceTests(unittest.TestCase):
    def test_healthy_sustained_exact_run_can_pass(self) -> None:
        result = analyze(
            telemetry(),
            scenario="1080p30_to_4k60",
            minimum_seconds=1800,
            quality_passed=True,
        )
        self.assertTrue(result["passed"])
        self.assertEqual("exact-run-pass-not-global", result["physical_acceptance"])
        self.assertFalse(result["system_mutations_performed"])
        self.assertEqual(6.0, result["evidence"]["throughput"]["stages"]["IA 2/3"]["units_per_second"])

    def test_missing_quality_gate_rejects_even_if_fast_and_cool(self) -> None:
        result = analyze(
            telemetry(),
            scenario="720p24_to_8k120_music",
            minimum_seconds=1800,
            quality_passed=False,
        )
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["quality_and_integrity_passed"])

    def test_short_or_hot_run_cannot_be_called_overnight_accepted(self) -> None:
        result = analyze(
            telemetry(wall=300.0, temp=91.0, sample_count=150),
            scenario="1080p30_to_4k60",
            minimum_seconds=1800,
            quality_passed=True,
        )
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["sustained_duration"])
        self.assertFalse(result["checks"]["no_critical_gpu_heat"])

    def test_sparse_telemetry_rejects_instead_of_extrapolating(self) -> None:
        result = analyze(
            telemetry(sample_count=10),
            scenario="1080p30_to_4k60",
            minimum_seconds=1800,
            quality_passed=True,
        )
        self.assertFalse(result["checks"]["telemetry_coverage"])
        self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main()
