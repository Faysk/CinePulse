from __future__ import annotations

import logging
import sys
from pathlib import Path

from . import __version__
from .paths import PATHS, ensure_runtime_directories
from .recovery_bootstrap import run_recovery_bootstrap
from .runtime_distribution import InstanceGuard


def _configure_logging() -> Path:
    ensure_runtime_directories()
    log_path = PATHS.logs / "cinepulse.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    guard = InstanceGuard(PATHS.locks / "app-instance.json")
    if not guard.acquire():
        logging.getLogger(__name__).warning("Segunda instância bloqueada; lock=%s", PATHS.locks)
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, "O CinePulse já está aberto nesta sessão.", "CinePulse", 0x40)
            except Exception:
                pass
        return
    try:
        logging.getLogger(__name__).info(
            "Iniciando CinePulse %s; dados=%s; log=%s",
            __version__, PATHS.data, log_path,
        )
        try:
            bootstrap = run_recovery_bootstrap(PATHS.data, PATHS.logs, PATHS.config)
            logging.getLogger(__name__).info(
                "Recovery rollout ring=%s mode=%s discovered=%s",
                bootstrap.flags.ring,
                bootstrap.mode,
                bootstrap.discovered,
            )
        except Exception as exc:
            # Discovery is observational during rollout. It must never prevent
            # the legacy application from starting or mutate recoverable data.
            logging.getLogger(__name__).exception("Recovery bootstrap dry-run failed: %s", exc)
        from .studio import main as studio_main

        studio_main()
    finally:
        guard.release()
