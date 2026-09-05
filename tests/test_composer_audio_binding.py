from __future__ import annotations

import math
import unittest

import numpy as np

from cinepulse.composer_audio import analyze_visualizer_samples
from cinepulse.composer_audio_binding import composer_audio_features, required_analysis_bands
from cinepulse.composer_runtime import ComposerFrameInputs, render_composer_frame
from cinepulse.music_envelope import SAMPLE_RATE
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState, VisualizerLayer


class ComposerAudioBindingTests(unittest.TestCase):
    @staticmethod
    def envelope(frequency: float, *, duration: float = 0.8):
        time = np.arange(int(SAMPLE_RATE * duration), dtype=np.float32) / SAMPLE_RATE
        samples = (0.7 * np.sin(2.0 * math.pi * frequency * time)).astype(np.float32)
        return analyze_visualizer_samples(samples, duration, fps=20, bands=64, waveform_rate=480)

    def test_each_visualizer_gets_its_own_signal_shape_on_same_master(self) -> None:
        state = OverlayComposerState([
            ComposerItem("wave", visualizer=VisualizerLayer("waveform", binding="master", bars=32)),
            ComposerItem("spec", visualizer=VisualizerLayer("spectrum", binding="master", bars=64)),
        ])
        features = composer_audio_features(state, {"master": self.envelope(440.0)}, project_time=0.4)
        self.assertIn("master", features)
        self.assertEqual(32, len(features["wave"].values))
        self.assertEqual(64, len(features["spec"].values))
        self.assertNotEqual(features["wave"].values[:8], features["spec"].values[:8])
        self.assertAlmostEqual(features["wave"].rms, features["spec"].rms, places=6)

    def test_exact_stem_wins_and_missing_stem_falls_back_to_master(self) -> None:
        state = OverlayComposerState([
            ComposerItem("drums", visualizer=VisualizerLayer("spectrum", binding="drums", bars=16)),
            ComposerItem("vocals", visualizer=VisualizerLayer("spectrum", binding="vocals", bars=16)),
        ])
        master = self.envelope(220.0)
        drums = self.envelope(4000.0)
        features = composer_audio_features(state, {"master": master, "drums": drums}, project_time=0.35)
        self.assertEqual(16, len(features["drums"].values))
        self.assertEqual(16, len(features["vocals"].values))
        self.assertNotEqual(features["drums"].values, features["vocals"].values)
        self.assertEqual(features["vocals"].values, composer_audio_features(
            OverlayComposerState([ComposerItem("v", visualizer=VisualizerLayer("spectrum", binding="master", bars=16))]),
            {"master": master}, project_time=0.35,
        )["v"].values)

    def test_required_bands_track_largest_visualizer_for_binding(self) -> None:
        state = OverlayComposerState([
            ComposerItem("a", visualizer=VisualizerLayer("spectrum", binding="master", bars=32)),
            ComposerItem("b", visualizer=VisualizerLayer("circular", binding="master", bars=128)),
            ComposerItem("c", visualizer=VisualizerLayer("spectrum", binding="drums", bars=64)),
        ])
        self.assertEqual(128, required_analysis_bands(state, "master"))
        self.assertEqual(64, required_analysis_bands(state, "drums"))
        self.assertEqual(16, required_analysis_bands(state, "vocals"))

    def test_runtime_uses_item_specific_features_before_binding_fallback(self) -> None:
        state = OverlayComposerState([
            ComposerItem("quiet", visualizer=VisualizerLayer("spectrum", binding="master", bars=8, z_order=0)),
            ComposerItem("hot", visualizer=VisualizerLayer("spectrum", binding="master", bars=8, z_order=1)),
        ])
        from cinepulse.composer_runtime import AudioFrameFeatures
        audio = {
            "master": AudioFrameFeatures(rms=0.0, onset=0.0, band_energy=0.0, values=(0.0,) * 8),
            "quiet": AudioFrameFeatures(rms=0.0, onset=0.0, band_energy=0.0, values=(0.0,) * 8),
            "hot": AudioFrameFeatures(rms=1.0, onset=1.0, band_energy=1.0, values=(1.0,) * 8),
        }
        base = np.zeros((48, 48, 3), dtype=np.uint8)
        rendered = render_composer_frame(base, state, ComposerFrameInputs(0.0, {}, audio))
        self.assertGreater(int(rendered[..., :3].max()), 0)


if __name__ == "__main__":
    unittest.main()
