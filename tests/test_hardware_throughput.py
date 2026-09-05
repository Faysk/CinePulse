from __future__ import annotations

import unittest

from cinepulse.hardware_throughput import derive_stage_throughput, throughput_from_telemetry


class HardwareThroughputTests(unittest.TestCase):
    def test_neural_chunks_sum_real_event_frames_over_measured_wall_time(self) -> None:
        events = [
            {"stage": "IA 2/3", "detail": "Lote 1: Real-ESRGAN em 40 quadro(s)."},
            {"stage": "IA 2/3", "detail": "Lote 2: Real-ESRGAN em 32 quadro(s)."},
        ]
        summary = {"IA 2/3": {"wall_seconds": 12.0}}
        result = derive_stage_throughput(events, summary)["IA 2/3"]
        self.assertEqual(72, result["work_units"])
        self.assertEqual("frames", result["work_unit"])
        self.assertEqual(6.0, result["units_per_second"])
        self.assertEqual(2, result["evidence_events"])

    def test_rife_and_extract_events_use_their_own_stage_names(self) -> None:
        events = [
            {"stage": "RIFE 1/3", "detail": "Lote 1: extraindo 12 quadro(s) fonte."},
            {"stage": "RIFE 2/3", "detail": "Lote 1: gerando 48 quadros com rife-v4.6."},
        ]
        summary = {
            "RIFE 1/3": {"wall_seconds": 3.0},
            "RIFE 2/3": {"wall_seconds": 8.0},
        }
        result = derive_stage_throughput(events, summary)
        self.assertEqual(4.0, result["RIFE 1/3"]["units_per_second"])
        self.assertEqual(6.0, result["RIFE 2/3"]["units_per_second"])

    def test_stage_without_explicit_work_is_omitted_instead_of_estimated(self) -> None:
        payload = {
            "stage_events": [{"stage": "Codificando", "detail": "Preparando saída final."}],
            "summary": {"stages": {"Codificando": {"wall_seconds": 2.0}}},
        }
        result = throughput_from_telemetry(payload)
        self.assertFalse(result["estimated"])
        self.assertEqual({}, result["stages"])

    def test_zero_wall_time_cannot_create_infinite_throughput(self) -> None:
        result = derive_stage_throughput(
            [{"stage": "IA 2/3", "detail": "Real-ESRGAN em 10 quadro(s)."}],
            {"IA 2/3": {"wall_seconds": 0.0}},
        )
        self.assertEqual({}, result)


if __name__ == "__main__":
    unittest.main()
