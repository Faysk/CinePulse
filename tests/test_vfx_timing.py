from __future__ import annotations

import unittest

from cinepulse.vfx import build_vfx_filter_graph


class VfxTimingTests(unittest.TestCase):
    def test_overlay_explicitly_repeats_last_effect_frame_without_shortening_base(self) -> None:
        graph = build_vfx_filter_graph(1920, 1080)
        self.assertIn("eof_action=repeat", graph)
        self.assertIn("shortest=0", graph)
        self.assertIn("repeatlast=1", graph)


if __name__ == "__main__":
    unittest.main()
