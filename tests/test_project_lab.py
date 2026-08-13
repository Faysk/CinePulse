from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from cinepulse.ui.preview import demo_background
from cinepulse.ui.project_lab import (
    framing_explanation,
    framing_preview,
    framing_retention,
    output_state,
    summarize_audio_probe,
    summarize_video_probe,
    target_ratio,
)


class ProjectLabTests(unittest.TestCase):
    def test_video_probe_becomes_compact_user_summary(self) -> None:
        data = {
            "format": {"duration": "12.4"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "profile": "High",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                    "pix_fmt": "yuv420p",
                    "color_primaries": "bt709",
                    "color_transfer": "bt709",
                    "color_space": "bt709",
                    "color_range": "tv",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 2,
                    "sample_rate": "48000",
                },
            ],
        }
        summary = summarize_video_probe(data)
        self.assertIn("1920×1080", summary.headline)
        self.assertIn("29.97 fps", summary.headline)
        self.assertIn("H264 High", summary.detail)
        self.assertIn("SDR", summary.detail)
        self.assertIn("AAC", summary.detail)

    def test_audio_probe_becomes_compact_user_summary(self) -> None:
        data = {
            "format": {"duration": "222.0"},
            "streams": [{
                "codec_type": "audio",
                "codec_name": "flac",
                "channels": 2,
                "sample_rate": "48000",
                "bit_rate": "1411200",
            }],
        }
        summary = summarize_audio_probe(data)
        self.assertIn("03:42", summary.headline)
        self.assertIn("FLAC", summary.headline)
        self.assertIn("48 kHz", summary.headline)
        self.assertIn("estéreo", summary.detail)

    def test_output_state_catches_collision_and_accepts_existing_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            source.write_bytes(b"x")
            state, _title, _detail = output_state(str(source), str(source), "")
            self.assertEqual("error", state)
            state, title, _detail = output_state(str(root / "result.mp4"), str(source), "")
            self.assertEqual("ok", state)
            self.assertIn("Destino pronto", title)

    def test_framing_geometry_distinguishes_cover_and_contain(self) -> None:
        source = demo_background(480, 270)
        cover = framing_preview(
            source,
            "9:16 — vertical",
            "Preencher a tela — cortar bordas",
            source_width=1920,
            source_height=1080,
        )
        contain = framing_preview(
            source,
            "9:16 — vertical",
            "Encaixar inteiro — usar barras",
            source_width=1920,
            source_height=1080,
        )
        self.assertEqual((360, 640, 3), cover.shape)
        self.assertEqual((360, 640, 3), contain.shape)
        self.assertFalse(np.array_equal(cover, contain))

    def test_framing_retention_and_explanation_are_honest(self) -> None:
        ratio = target_ratio("9:16 — vertical", 1920, 1080)
        kept = framing_retention(1920, 1080, ratio, True)
        self.assertLess(kept, 0.4)
        text = framing_explanation(
            1920,
            1080,
            "9:16 — vertical",
            "Preencher a tela — cortar bordas",
        )
        self.assertIn("corta aproximadamente", text)


if __name__ == "__main__":
    unittest.main()
