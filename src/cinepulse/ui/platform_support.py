"""Small platform hooks used by the desktop shell."""

from __future__ import annotations

import os


def enable_windows_dpi_awareness() -> str:
    """Ask Windows for per-monitor DPI awareness before Tk is created.

    The function is best-effort because older Windows versions expose only the
    legacy process-wide API.  Failure must never prevent the application from
    opening.
    """
    if os.name != "nt":
        return "not-windows"
    try:
        import ctypes

        try:
            shcore = ctypes.windll.shcore
            result = int(shcore.SetProcessDpiAwareness(2))  # PROCESS_PER_MONITOR_DPI_AWARE
            if result in (0, -2147024891):  # S_OK or already configured/access denied by host
                return "per-monitor"
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            return "system"
        except Exception:
            return "unavailable"
    except Exception:
        return "unavailable"
