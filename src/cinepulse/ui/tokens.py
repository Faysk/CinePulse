"""Design tokens da interface CinePulse.

Os valores seguem a identidade registrada em ``docs/BRAND.md`` e concentram
cores/espacamentos que antes estavam espalhados pelo ``studio.py``.
"""

from __future__ import annotations

COLORS = {
    # Marca
    "pulse_blue": "#42D8FF",
    "ai_violet": "#8B5CF6",
    "audio_green": "#37F5B0",
    "cinema": "#080B12",
    # Light
    "light_bg": "#F7F9FC",
    "light_panel": "#FFFFFF",
    "light_panel_alt": "#F2F5FA",
    "light_field": "#FFFFFF",
    "light_border": "#D9E1EC",
    "light_text": "#151922",
    "light_muted": "#667085",
    "light_muted_2": "#98A2B3",
    # Dark
    "dark_bg": "#0B1018",
    "dark_panel": "#111824",
    "dark_panel_alt": "#172131",
    "dark_field": "#0E1622",
    "dark_border": "#26364B",
    "dark_text": "#F5F7FB",
    "dark_muted": "#A9B5C6",
    "dark_muted_2": "#728198",
    # Estados
    "primary": "#1473E6",
    "primary_hover": "#0B63CE",
    "primary_pressed": "#0954AF",
    "success": "#17A673",
    "warning": "#D98E04",
    "danger": "#D92D20",
    "danger_hover": "#B42318",
}

SPACING = {
    "2xs": 2,
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 20,
    "2xl": 24,
    "3xl": 32,
}

RADIUS = {
    "sm": 6,
    "md": 10,
    "lg": 14,
}

FONT = {
    "family": "Segoe UI",
    "title": 21,
    "section": 11,
    "body": 10,
    "small": 9,
}
