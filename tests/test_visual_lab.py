import unittest

import numpy as np

from cinepulse.ui.preview import demo_background, demo_reactivity, visual_preview
from cinepulse.ui.visual_lab import TRANSITION_SHORTLIST, VISUAL_VARIANTS, transition_thumbnail, variant_preview


class VisualLabTests(unittest.TestCase):
    def test_demo_reactivity_changes_with_focus(self):
        bass, loud_bass, attack_bass = demo_reactivity(113, focus="Graves", smoothing=0.82, expression=0.82)
        highs, loud_high, attack_high = demo_reactivity(113, focus="Agudos", smoothing=0.82, expression=0.82)
        self.assertEqual(bass.shape, (3,))
        self.assertEqual(highs.shape, (3,))
        self.assertFalse(np.allclose(bass, highs))
        self.assertNotEqual(round(loud_bass, 5), round(loud_high, 5))
        self.assertGreaterEqual(attack_bass, 0)
        self.assertGreaterEqual(attack_high, 0)

    def test_interactive_preview_reactivity_changes_pixels(self):
        base = demo_background(320, 180)
        low = visual_preview(
            {"Espectro", "Pulso cinematográfico"}, "#43D6FF", 1.0, 0.65,
            base_rgb=base, width=320, height=180, frame_number=80,
            focus="Graves", smoothing=0.90, expression=0.55,
        )
        energetic = visual_preview(
            {"Espectro", "Pulso cinematográfico"}, "#43D6FF", 1.0, 0.65,
            base_rgb=base, width=320, height=180, frame_number=80,
            focus="Batidas e ataques", smoothing=0.30, expression=1.50,
        )
        self.assertFalse(np.array_equal(low, energetic))

    def test_transition_shortlist_produces_distinct_rgb_guides(self):
        images = [transition_thumbnail(label, 120, 68) for label in TRANSITION_SHORTLIST]
        for image in images:
            self.assertEqual(image.shape, (68, 120, 3))
            self.assertEqual(image.dtype, np.uint8)
        signatures = {image.tobytes() for image in images}
        self.assertEqual(len(signatures), len(images))

    def test_variants_are_visually_distinct(self):
        base = demo_background(220, 124)
        images = []
        for variant in VISUAL_VARIANTS:
            images.append(
                variant_preview(
                    variant.key,
                    {"Aurora", "Partículas musicais", "Pulso cinematográfico"},
                    "#43D6FF",
                    1.0,
                    0.65,
                    base_rgb=base,
                    frame_number=141,
                    focus="Graves e batidas",
                    smoothing=0.82,
                    expression=0.82,
                )
            )
        signatures = {image.tobytes() for image in images}
        self.assertEqual(len(signatures), len(images))


if __name__ == "__main__":
    unittest.main()
