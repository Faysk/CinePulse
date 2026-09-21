from __future__ import annotations

import unittest

from cinepulse.audio_mastering import (
    bound_delivery_audio_filter,
    bounded_audio_input_args,
    build_audio_filter,
    build_delivery_audio_filter,
    frame_bound_duration,
    parse_loudnorm_json,
)


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

    def test_frame_bound_duration_matches_integer_cfr_contract(self) -> None:
        self.assertAlmostEqual(1001 / 120.0, frame_bound_duration(1001, 120.0), places=12)

    def test_delivery_audio_filter_trims_resets_and_pads_exact_timeline(self) -> None:
        value = bound_delivery_audio_filter(1.25, "volume=0.5")
        self.assertEqual(
            "atrim=duration=1.250000000000,asetpts=PTS-STARTPTS,volume=0.5,atrim=duration=1.250000000000,apad=whole_dur=1.250000000000",
            value,
        )

    def test_mastered_delivery_audio_wraps_mastering_inside_exact_timeline(self) -> None:
        value = build_delivery_audio_filter("Normalizar para YouTube — -14 LUFS", 2.0)
        self.assertTrue(value.startswith("atrim=duration=2.000000000000,asetpts=PTS-STARTPTS,"))
        self.assertIn("loudnorm=I=-14.0:TP=-1.0:LRA=11.0", value)
        self.assertTrue(value.endswith("atrim=duration=2.000000000000,apad=whole_dur=2.000000000000"))

    def test_parses_ffmpeg_measurement(self) -> None:
        text = 'noise\n{"input_i":"-18.2","input_tp":"-2.1","input_lra":"4.3","input_thresh":"-28.0","target_offset":"0.2"}'
        measured = parse_loudnorm_json(text)
        self.assertEqual(-18.2, measured["input_i"])

    def test_second_pass_filter_uses_measurements(self) -> None:
        measured = {"input_i": -18.2, "input_tp": -2.1, "input_lra": 4.3, "input_thresh": -28.0, "target_offset": 0.2}
        audio_filter = build_audio_filter("Normalizar para YouTube — -14 LUFS", measured)
        self.assertIn("measured_I=-18.2", audio_filter)
        self.assertIn("linear=true", audio_filter)

