from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cinepulse.composer_export import ComposerBaseProfile
from cinepulse.composer_preview import (
    _base_preview_command,
    fit_preview_canvas,
    render_composer_preview,
)
from cinepulse.gpu_compositor import OverlayLayer
from cinepulse.overlay_composer import ComposerItem, OverlayComposerState


class ComposerPreviewCommandTests(unittest.TestCase):
    def test_preview_selects_exact_output_frame_and_explicit_bt709_conversion(self) -> None:
        profile = ComposerBaseProfile(
            1920, 1080, 60.0, 10.0, "yuv420p", "bt709", "bt709", "bt709", "tv"
        )
        command = _base_preview_command(
            "ffmpeg",
            "source.mkv",
            profile,
            123,
            target_width=960,
            target_height=540,
        )
        joined = " ".join(command)
        self.assertIn("select=eq(n\\,123)", joined)
        self.assertIn("scale=w=960:h=540", joined)
        self.assertIn("in_color_matrix=bt709", joined)
        self.assertIn("out_color_matrix=bt709", joined)
        self.assertIn("in_range=tv", joined)
        self.assertIn("out_range=pc", joined)
        self.assertIn("format=rgba", joined)
        self.assertIn("-frames:v 1", joined)
        self.assertNotIn(" -r ", joined)

    def test_preview_canvas_never_allocates_final_8k_or_12k_rgba(self) -> None:
        self.assertEqual((960, 540, 0.125), fit_preview_canvas(7680, 4320))
        width, height, scale = fit_preview_canvas(11520, 6480)
        self.assertEqual((960, 540), (width, height))
        self.assertAlmostEqual(1.0 / 12.0, scale, places=12)

    def test_preview_canvas_preserves_smaller_sources_without_upscale(self) -> None:
        self.assertEqual((640, 360, 1.0), fit_preview_canvas(640, 360))
        with self.assertRaises(ValueError):
            fit_preview_canvas(7680, 4320, max_width=0, max_height=540)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/FFprobe required")
class ComposerPreviewIntegrationTests(unittest.TestCase):
    def test_real_preview_renders_one_composed_rgba_frame(self) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        ffprobe = shutil.which("ffprobe") or "ffprobe"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mkv"
            logo = root / "logo.png"
            subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=blue:s=64x36:r=4:d=1",
                    "-c:v", "ffv1", "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    str(source),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=red@0.75:s=8x8:d=1,format=rgba",
                    "-frames:v", "1", str(logo),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            state = OverlayComposerState([
                ComposerItem(
                    "logo",
                    media=OverlayLayer(str(logo), "png", x=0.5, y=0.5, blend="screen"),
                )
            ])
            profile = ComposerBaseProfile(
                64, 36, 4.0, 1.0, "yuv420p", "bt709", "bt709", "bt709", "tv"
            )
            result = render_composer_preview(
                source=source,
                profile=profile,
                state=state,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                project_time=0.5,
            )
            self.assertEqual((36, 64, 4), result.rgba.shape)
            self.assertEqual((64, 36), (result.canvas_width, result.canvas_height))
            self.assertEqual(1.0, result.resolution_scale)
            self.assertEqual(2, result.frame_index)
            self.assertEqual(1, result.media_layers)
            self.assertEqual(0, result.visualizers)
            self.assertEqual(255, int(result.rgba[..., 3].min()))
            center = result.rgba[18, 32, :3]
            self.assertGreater(int(center[0]), 0)
            self.assertGreater(int(center[2]), 0)

    def test_real_preview_can_force_a_smaller_canvas(self) -> None:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        ffprobe = shutil.which("ffprobe") or "ffprobe"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mkv"
            logo = root / "logo.png"
            subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=64x36:r=2:d=1",
                    "-c:v", "ffv1", "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                    str(source),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=white:s=16x8:d=1,format=rgba",
                    "-frames:v", "1", str(logo),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            state = OverlayComposerState([
                ComposerItem("logo", media=OverlayLayer(str(logo), "png"))
            ])
            profile = ComposerBaseProfile(
                64, 36, 2.0, 1.0, "yuv420p", "bt709", "bt709", "bt709", "tv"
            )
            result = render_composer_preview(
                source=source,
                profile=profile,
                state=state,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                project_time=0.0,
                max_width=32,
                max_height=18,
            )
            self.assertEqual((18, 32, 4), result.rgba.shape)
            self.assertEqual((32, 18), (result.canvas_width, result.canvas_height))
            self.assertEqual(0.5, result.resolution_scale)


if __name__ == "__main__":
    unittest.main()
