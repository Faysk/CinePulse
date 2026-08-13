from __future__ import annotations

import unittest

from cinepulse.studio import FIT_CONTAIN, FIT_COVER, VideoOptimizerStudio
from cinepulse.vfx import build_vfx_filter_graph


class PipelinePreservationTests(unittest.TestCase):
    def setUp(self):
        self.studio = VideoOptimizerStudio.__new__(VideoOptimizerStudio)

    def test_equal_fps_does_not_insert_fps_or_minterpolate_filter(self):
        chain = self.studio._scale_filter(
            1920, 1080, 120.0, FIT_CONTAIN, 120.0, "Movimento suave — FFmpeg",
            spatial_mode="lanczos", source_size=(1920, 1080),
        )
        self.assertNotIn("minterpolate=", chain)
        self.assertNotIn("fps=120", chain)

    def test_lower_target_fps_uses_explicit_downsample(self):
        chain = self.studio._scale_filter(
            1920, 1080, 60.0, FIT_CONTAIN, 120.0, "RIFE IA — movimento natural",
            spatial_mode="lanczos", source_size=(1920, 1080),
        )
        self.assertIn("fps=60.00000000", chain)
        self.assertNotIn("minterpolate=", chain)

    def test_preserve_720p_inside_4k_canvas_does_not_scale_pixels_up(self):
        chain = self.studio._scale_filter(
            3840, 2160, 60.0, FIT_CONTAIN, 60.0, "Movimento suave — FFmpeg",
            spatial_mode="preserve", source_size=(1280, 720),
        )
        self.assertIn("scale=1280:720", chain)
        self.assertIn("pad=3840:2160", chain)
        self.assertNotIn("scale=3840:2160:force_original_aspect_ratio", chain)

    def test_lanczos_720p_to_4k_explicitly_scales_to_target(self):
        chain = self.studio._scale_filter(
            3840, 2160, 60.0, FIT_CONTAIN, 60.0, "Movimento suave — FFmpeg",
            spatial_mode="lanczos", source_size=(1280, 720),
        )
        self.assertIn("scale=3840:2160:force_original_aspect_ratio=decrease", chain)

    def test_preserve_cover_falls_back_to_no_upscale_when_native_pixels_are_insufficient(self):
        chain = self.studio._scale_filter(
            1080, 1920, 60.0, FIT_COVER, 60.0, "Movimento suave — FFmpeg",
            spatial_mode="preserve", source_size=(1920, 1080),
        )
        self.assertIn("scale=1080:608", chain)
        self.assertIn("pad=1080:1920", chain)
        self.assertNotIn("crop=1080:1920", chain)

    def test_vfx_graph_no_longer_retimes_base_to_60(self):
        graph = build_vfx_filter_graph(3840, 2160, 3840, 2160)
        self.assertIn("[0:v]format=yuv420p,setpts=PTS-STARTPTS[base]", graph)
        self.assertNotIn("N/(60*TB)", graph)
        self.assertNotIn("scale=3840:2160", graph)

    def test_vfx_graph_only_scales_when_adaptive_canvas_is_smaller(self):
        graph = build_vfx_filter_graph(7680, 4320, 3840, 2160)
        self.assertIn("scale=7680:4320:flags=lanczos", graph)
        self.assertNotIn("N/(60*TB)", graph)

    def test_vfx_graph_can_preserve_10bit_sdr_base(self):
        graph = build_vfx_filter_graph(
            3840, 2160, 3840, 2160,
            output_pixel_format="yuv420p10le",
            output_primaries="bt709",
            output_transfer="bt709",
            output_space="bt709",
            output_range="tv",
        )
        self.assertIn("[0:v]format=yuv420p10le", graph)
        self.assertIn("format=yuv420p10le,setparams=range=limited", graph)


if __name__ == "__main__":
    unittest.main()
