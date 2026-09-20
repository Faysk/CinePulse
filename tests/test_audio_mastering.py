from __future__ import annotations

import unittest

from cinepulse.audio_mastering import bounded_audio_input_args, build_audio_filter, parse_loudnorm_json


class AudioMasteringTests(unittest.TestCase):
    def test_bounded_audio_input_is_input_local(self) -> None:
        self.assertEqual(
            ["-t", "12.345679", "-i", "track.wav"],
            bounded_audio_input_args("track.wav", 12.3456789),
        )

    def test_bounded_audio_input_rejects_invalid_duration(self) -> None:
        for value in (0.0, -1.0, float("inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    bounded_audio_input_args("track.wav", value)

    def test_parses_ffmpeg_measurement(self) -> None:
        text = 'noise\n{"input_i":"-18.2","input_tp":"-2.1","input_lra":"4.3","input_thresh":"-28.0","target_offset":"0.2"}'
        measured = parse_loudnorm_json(text)
        self.assertEqual(-18.2, measured["input_i"])

    def test_second_pass_filter_uses_measurements(self) -> None:
        measured = {"input_i": -18.2, "input_tp": -2.1, "input_lra": 4.3, "input_thresh": -28.0, "target_offset": 0.2}
        audio_filter = build_audio_filter("Normalizar para YouTube — -14 LUFS", measured)
        self.assertIn("measured_I=-18.2", audio_filter)
        self.assertIn("linear=true", audio_filter)

