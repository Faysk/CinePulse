from __future__ import annotations

import inspect
import unittest

import cinepulse.vfx as vfx_module
from cinepulse.vfx import build_vfx_filter_graph


class VfxTimingTests(unittest.TestCase):
    def test_vfx_has_one_shot_cpu_encoder_fallbacks(self) -> None:
        source = inspect.getsource(vfx_module.render_vfx_intermediate)
        self.assertIn("fallback_video_args: list[str] | None = None", source)
        self.assertIn("VFX intermediário: H.264 NVENC falhou; repetindo com libx264.", source)
        self.assertIn("VFX fused: NVENC final falhou; repetindo entrega com encoder CPU equivalente.", source)
        self.assertIn("attempts = [primary_video_args]", source)
        self.assertIn("attempts.append(fallback_args)", source)
        self.assertIn("if return_code == 0:", source)
        self.assertNotIn("while True", source)

    def test_direct_nvenc_fallback_has_explicit_gpu_selection(self) -> None:
        source = inspect.getsource(vfx_module.render_vfx_intermediate)
        self.assertIn("gpu_index: int = 0", source)
        self.assertIn('"h264_nvenc"', source)
        self.assertIn('str(max(0, int(gpu_index)))', source)

    def test_overlay_explicitly_repeats_last_effect_frame_without_shortening_base(self) -> None:
        graph = build_vfx_filter_graph(1920, 1080)
        self.assertIn("eof_action=repeat", graph)
        self.assertIn("shortest=0", graph)
        self.assertIn("repeatlast=1", graph)


if __name__ == "__main__":
    unittest.main()
