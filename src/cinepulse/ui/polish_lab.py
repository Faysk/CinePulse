"""Pure helpers for Phase 8 release-UX polish.

This module deliberately avoids importing Tk so geometry, persistence and
responsive decisions stay deterministic and unit-testable.
"""

from __future__ import annotations

import re
from typing import Any

UI_STATE_SCHEMA = 1
DEFAULT_MIN_SIZE = (1024, 700)
COMPACT_WIDTH = 1180
COMPACT_HEIGHT = 760

SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("F1", "Abrir primeiros passos"),
    ("Ctrl+1 … Ctrl+6", "Ir direto para uma aba"),
    ("Ctrl+Tab", "Próxima aba"),
    ("Ctrl+Shift+Tab", "Aba anterior"),
    ("Ctrl+O", "Selecionar vídeo"),
    ("Ctrl+Shift+O", "Selecionar música"),
    ("Ctrl+Shift+S", "Escolher arquivo de saída"),
    ("Ctrl+P", "Gerar preview renderizado"),
    ("Ctrl+L", "Abrir log"),
    ("Ctrl+Shift+A", "Abrir Central de atividade"),
)

_GEOMETRY_RE = re.compile(r"^(?P<w>\d+)x(?P<h>\d+)(?:(?P<x>[+-]\d+)(?P<y>[+-]\d+))?$")


def sanitize_ui_state(payload: Any) -> dict[str, Any]:
    """Return a conservative, forward-compatible UI-state dictionary."""
    if not isinstance(payload, dict):
        payload = {}
    result: dict[str, Any] = {"schema": UI_STATE_SCHEMA}
    result["dark_mode"] = bool(payload.get("dark_mode", False))
    result["welcome_completed"] = bool(payload.get("welcome_completed", False))
    try:
        last_tab = int(payload.get("last_tab", 0))
    except (TypeError, ValueError):
        last_tab = 0
    result["last_tab"] = max(0, min(5, last_tab))
    geometry = payload.get("geometry", "")
    result["geometry"] = str(geometry).strip() if isinstance(geometry, str) else ""
    return result


def safe_window_geometry(
    saved: str,
    *,
    screen_width: int,
    screen_height: int,
    fallback_width: int,
    fallback_height: int,
    min_width: int = DEFAULT_MIN_SIZE[0],
    min_height: int = DEFAULT_MIN_SIZE[1],
) -> str:
    """Clamp persisted geometry to the currently available screen.

    We keep the whole title bar reachable and refuse values that would restore
    an unusably small/off-screen window after monitor or DPI changes.
    """
    screen_width = max(min_width, int(screen_width or min_width))
    screen_height = max(min_height, int(screen_height or min_height))
    fallback_width = max(min_width, min(int(fallback_width), screen_width))
    fallback_height = max(min_height, min(int(fallback_height), screen_height))

    match = _GEOMETRY_RE.match(str(saved or "").strip())
    if not match:
        return f"{fallback_width}x{fallback_height}"

    width = max(min_width, min(int(match.group("w")), screen_width))
    height = max(min_height, min(int(match.group("h")), screen_height))
    x_text = match.group("x")
    y_text = match.group("y")
    if x_text is None or y_text is None:
        return f"{width}x{height}"

    x = int(x_text)
    y = int(y_text)
    # Keep the whole window on the current screen whenever possible.  This
    # handles monitor removal and DPI changes without stranding controls.
    x = max(0, min(x, max(0, screen_width - width)))
    y = max(0, min(y, max(0, screen_height - height)))
    return f"{width}x{height}+{x}+{y}"


def compact_layout(width: int, height: int) -> bool:
    """Whether split workspaces should stack for the current client size."""
    return int(width or 0) < COMPACT_WIDTH or int(height or 0) < COMPACT_HEIGHT


def tab_for_shortcut(number: int) -> int | None:
    """Translate user-facing 1-based tab shortcuts to notebook indexes."""
    try:
        number = int(number)
    except (TypeError, ValueError):
        return None
    if 1 <= number <= 6:
        return number - 1
    return None
