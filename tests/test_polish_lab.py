from __future__ import annotations

import unittest

from cinepulse.ui.platform_support import enable_windows_dpi_awareness
from cinepulse.ui.polish_lab import (
    SHORTCUTS,
    compact_layout,
    safe_window_geometry,
    sanitize_ui_state,
    tab_for_shortcut,
)


class PolishLabTests(unittest.TestCase):
    def test_state_is_bounded_and_forward_compatible(self):
        state = sanitize_ui_state(
            {
                "dark_mode": 1,
                "welcome_completed": "yes",
                "last_tab": 99,
                "geometry": "1400x900+20+30",
                "future": "ignored",
            }
        )
        self.assertTrue(state["dark_mode"])
        self.assertTrue(state["welcome_completed"])
        self.assertEqual(state["last_tab"], 5)
        self.assertEqual(state["geometry"], "1400x900+20+30")
        self.assertNotIn("future", state)

    def test_saved_geometry_cannot_restore_off_screen(self):
        geometry = safe_window_geometry(
            "1600x1000-400+900",
            screen_width=1366,
            screen_height=768,
            fallback_width=1200,
            fallback_height=720,
        )
        self.assertEqual(geometry, "1366x768+0+0")

    def test_invalid_geometry_falls_back_to_supported_size(self):
        geometry = safe_window_geometry(
            "banana",
            screen_width=1920,
            screen_height=1080,
            fallback_width=1440,
            fallback_height=900,
        )
        self.assertEqual(geometry, "1440x900")

    def test_compact_layout_covers_minimum_window(self):
        self.assertTrue(compact_layout(1024, 700))
        self.assertTrue(compact_layout(1440, 720))
        self.assertFalse(compact_layout(1440, 900))

    def test_tab_shortcuts_are_one_based_and_bounded(self):
        self.assertEqual(tab_for_shortcut(1), 0)
        self.assertEqual(tab_for_shortcut(6), 5)
        self.assertIsNone(tab_for_shortcut(0))
        self.assertIsNone(tab_for_shortcut(7))

    def test_shortcut_reference_has_unique_user_facing_keys(self):
        keys = [key for key, _action in SHORTCUTS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_dpi_hook_is_best_effort(self):
        self.assertIn(enable_windows_dpi_awareness(), {"not-windows", "per-monitor", "system", "unavailable"})


if __name__ == "__main__":
    unittest.main()
