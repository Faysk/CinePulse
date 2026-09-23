from __future__ import annotations

import math
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from cinepulse.composer_audio import (
    analyze_visualizer_samples,
    clear_visualizer_memory_cache,
    frame_audio,
    load_visualizer_envelope,
)
from cinepulse.music_envelope import SAMPLE_RATE

class ComposerAudioTests(unittest.TestCase):
    @staticmethod
    def sine(frequency: float, duration: float = 1.2) -> np.ndarray:
        time = np.arange(int(SAMPLE_RATE * duration), dtype=np.float32) / SAMPLE_RATE
        return (0.72 * np.sin(2.0 * math.pi * frequency * time)).astype(np.float32)

    def test_spectrum_keeps_real_frequency_separation(self) -> None:
        low = analyze_visualizer_samples(self.sine(90.0), 1.2, fps=20, bands=64, waveform_rate=480)
        high = analyze_visualizer_samples(self.sine(5000.0), 1.2, fps=20, bands=64, waveform_rate=480)
        low_index = int(np.argmax(np.mean(low.spectrum[3:-3], axis=0)))
        high_index = int(np.argmax(np.mean(high.spectrum[3:-3], axis=0)))
        self.assertLess(low.frequencies[low_index], 180.0)
        self.assertGreater(high.frequencies[high_index], 3000.0)
        self.assertGreater(high_index, low_index + 20)

    def test_requested_bar_count_is_resampled_without_three_band_faking(self) -> None:
        envelope = analyze_visualizer_samples(self.sine(440.0), 1.2, fps=20, bands=64, waveform_rate=480)
        frame = frame_audio(envelope, time_seconds=0.6, kind="spectrum", bars=128, smoothing=0.3)
        self.assertEqual(128, len(frame.values))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in frame.values))
        self.assertGreater(max(frame.values), 0.5)

    def test_waveform_returns_signed_shape_mapped_around_midline(self) -> None:
        envelope = analyze_visualizer_samples(self.sine(220.0), 1.2, fps=20, bands=32, waveform_rate=960)
        frame = frame_audio(envelope, time_seconds=0.5, kind="waveform", bars=64)
        self.assertEqual(64, len(frame.values))
        self.assertLess(min(frame.values), 0.25)
        self.assertGreater(max(frame.values), 0.75)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in frame.values))

    def test_transient_produces_onset_peak(self) -> None:
        duration = 1.5
        samples = np.zeros(int(SAMPLE_RATE * duration), dtype=np.float32)
        start = int(0.72 * SAMPLE_RATE)
        width = int(0.018 * SAMPLE_RATE)
        samples[start : start + width] = np.hanning(width).astype(np.float32)
        envelope = analyze_visualizer_samples(samples, duration, fps=40, bands=32, waveform_rate=480)
        peak = int(np.argmax(envelope.onset)) / envelope.fps
        self.assertGreater(float(np.max(envelope.onset)), 0.75)
        self.assertLess(abs(peak - 0.72), 0.10)

    def test_smoothing_is_deterministic_for_random_seek(self) -> None:
        samples = self.sine(330.0, 1.5)
        envelope = analyze_visualizer_samples(samples, 1.5, fps=24, bands=32, waveform_rate=480)
        first = frame_audio(envelope, time_seconds=1.1, kind="circular", bars=48, smoothing=0.8)
        second = frame_audio(envelope, time_seconds=1.1, kind="circular", bars=48, smoothing=0.8)
        self.assertEqual(first, second)

    def test_concurrent_disk_cache_publication_uses_unique_temps(self) -> None:
        clear_visualizer_memory_cache()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media = root / "audio.wav"
            media.write_bytes(b"placeholder")
            cache = root / "cache"
            save_barrier = threading.Barrier(2)
            save_paths = []
            errors = []

            def fake_save(path, **_payload):
                save_paths.append(Path(path))
                save_barrier.wait(timeout=2.0)
                Path(path).write_bytes(b"cache")

            def worker():
                try:
                    load_visualizer_envelope(
                        "ffmpeg", str(media), 0.1,
                        analysis_fps=10.0, bands=8, waveform_rate=120.0, cache_dir=cache,
                    )
                except BaseException as exc:
                    errors.append(exc)

            with (
                mock.patch("cinepulse.composer_audio.decode_audio", return_value=np.zeros(4_800, dtype=np.float32)),
                mock.patch("cinepulse.composer_audio.np.savez_compressed", side_effect=fake_save),
            ):
                threads = [threading.Thread(target=worker) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=3.0)

            self.assertEqual([], errors)
            self.assertEqual(2, len(save_paths))
            self.assertNotEqual(save_paths[0], save_paths[1])
            self.assertEqual([], list(cache.glob("*.tmp.npz")))
        clear_visualizer_memory_cache()

    def test_analysis_shapes_are_bounded_and_float32(self) -> None:
        envelope = analyze_visualizer_samples(self.sine(1000.0, 0.5), 0.5, fps=30, bands=16, waveform_rate=240)
        self.assertEqual((15, 16), envelope.spectrum.shape)
        self.assertEqual((15,), envelope.rms.shape)
        self.assertEqual((15,), envelope.onset.shape)
        self.assertEqual(np.float32, envelope.spectrum.dtype)
        self.assertEqual(np.float32, envelope.waveform.dtype)
        self.assertTrue(np.all((envelope.spectrum >= 0) & (envelope.spectrum <= 1)))


if __name__ == "__main__":
    unittest.main()
