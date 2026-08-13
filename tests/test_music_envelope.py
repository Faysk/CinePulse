from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from cinepulse.music_envelope import (
    MusicEnvelope,
    analyze_music_structure,
    analyze_samples,
    clear_memory_cache,
    load_music_envelope,
    resample_features,
)
from cinepulse.vfx import StudioFrameGenerator
from cinepulse.vfx_policy import choose_vfx_render_spec


class MusicEnvelopeTests(unittest.TestCase):
    def tearDown(self):
        clear_memory_cache()

    def _envelope(self) -> MusicEnvelope:
        fps = 120.0
        frames = 1200
        t = np.arange(frames, dtype=np.float32) / fps
        bass = np.clip(0.15 + 0.75 * (t / t[-1]), 0, 1)
        mids = np.clip(0.4 + 0.2 * np.sin(t), 0, 1)
        highs = np.clip(0.3 + 0.15 * np.cos(t * 1.7), 0, 1)
        energy = np.column_stack((bass, mids, highs)).astype(np.float32)
        rms = np.clip(0.4 * bass + 0.35 * mids + 0.25 * highs, 0, 1).astype(np.float32)
        onset = np.clip(np.r_[0, np.diff(bass)] * 15, 0, 1).astype(np.float32)
        return MusicEnvelope(energy, rms, onset, fps, 10.0, "synthetic")

    def test_preview_slice_matches_same_timestamps_from_final_envelope(self):
        envelope = self._envelope()
        preview = envelope.shaped_slice(
            focus="Graves e batidas", smoothing=0.72, expression=1.1,
            target_fps=60.0, start=0.0, duration=2.0,
            dynamic_sections=True, section_dynamics=0.8,
        )
        final = envelope.shaped_slice(
            focus="Graves e batidas", smoothing=0.72, expression=1.1,
            target_fps=60.0, start=0.0, duration=10.0,
            dynamic_sections=True, section_dynamics=0.8,
        )
        self.assertTrue(np.allclose(preview.energy, final.energy[: len(preview.energy)], atol=1e-6))
        self.assertTrue(np.allclose(preview.rms, final.rms[: len(preview.rms)], atol=1e-6))
        self.assertTrue(np.allclose(preview.onset, final.onset[: len(preview.onset)], atol=1e-6))

    def test_resampling_produces_requested_native_120fps_count(self):
        envelope = self._envelope()
        energy, rms, onset = resample_features(
            envelope.energy, envelope.rms, envelope.onset,
            source_fps=120.0, target_fps=120.0, start=1.0, duration=2.0,
        )
        self.assertEqual(energy.shape, (240, 3))
        self.assertEqual(rms.shape, (240,))
        self.assertEqual(onset.shape, (240,))

    def test_music_structure_uses_supplied_fps_not_legacy_60(self):
        envelope = self._envelope()
        modulation, sections = analyze_music_structure(
            envelope.energy, envelope.rms, envelope.onset, 0.8, fps=120.0
        )
        self.assertEqual(len(modulation), len(envelope.rms))
        self.assertTrue(sections)
        self.assertAlmostEqual(sections[0][1], 6.0, places=3)

    def test_full_track_analysis_normalizes_against_late_loud_section(self):
        sample_rate = 48_000
        quiet = np.sin(np.arange(sample_rate, dtype=np.float32) * 2 * np.pi * 90 / sample_rate) * 0.05
        loud = np.sin(np.arange(sample_rate, dtype=np.float32) * 2 * np.pi * 90 / sample_rate) * 0.80
        samples = np.concatenate((quiet, loud)).astype(np.float32)
        energy, rms, _ = analyze_samples(samples, 2.0, fps=60.0)
        self.assertLess(float(np.mean(rms[:50])), float(np.mean(rms[70:])))
        self.assertLess(float(np.mean(energy[:50, 0])), float(np.mean(energy[70:, 0])))

    def test_disk_cache_reuses_analysis_without_decoding_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "audio.wav"
            media.write_bytes(b"placeholder")
            cache = Path(tmp) / "cache"
            synthetic = np.zeros(48_000, dtype=np.float32)
            with mock.patch("cinepulse.music_envelope.decode_audio", return_value=synthetic) as decode:
                first = load_music_envelope("ffmpeg", str(media), 1.0, analysis_fps=60.0, cache_dir=cache)
                self.assertEqual(decode.call_count, 1)
            clear_memory_cache()
            with mock.patch("cinepulse.music_envelope.decode_audio", side_effect=AssertionError("cache miss")):
                second = load_music_envelope("ffmpeg", str(media), 1.0, analysis_fps=60.0, cache_dir=cache)
            self.assertEqual(first.source_key, second.source_key)
            self.assertTrue(np.array_equal(first.energy, second.energy))


class VfxPolicyTests(unittest.TestCase):
    def test_1080p60_is_native_not_320x180(self):
        spec = choose_vfx_render_spec(1920, 1080, 60.0)
        self.assertEqual((spec.width, spec.height, spec.fps), (1920, 1080, 60.0))
        self.assertTrue(spec.native_spatial)
        self.assertTrue(spec.native_temporal)

    def test_4k120_is_native_spatial_and_temporal(self):
        spec = choose_vfx_render_spec(3840, 2160, 120.0)
        self.assertEqual((spec.width, spec.height, spec.fps), (3840, 2160, 120.0))
        self.assertTrue(spec.native_spatial)
        self.assertTrue(spec.native_temporal)

    def test_8k120_uses_deterministic_4k_class_canvas_not_legacy_canvas(self):
        spec = choose_vfx_render_spec(7680, 4320, 120.0)
        self.assertEqual((spec.width, spec.height), (3840, 2160))
        self.assertEqual(spec.fps, 120.0)
        self.assertFalse(spec.native_spatial)
        self.assertNotEqual((spec.width, spec.height), (320, 180))

    def test_generator_honors_requested_dimensions_and_cadence(self):
        generator = StudioFrameGenerator(
            {"Círculo mágico"}, "#42D8FF", 1.0, 0.65,
            width=640, height=360, fps=120.0,
        )
        frame = generator.make(120, np.asarray((0.7, 0.5, 0.4), dtype=np.float32), 0.6, 0.3)
        self.assertEqual(len(frame), 640 * 360 * 4)
        self.assertEqual(generator.fps, 120.0)


if __name__ == "__main__":
    unittest.main()
