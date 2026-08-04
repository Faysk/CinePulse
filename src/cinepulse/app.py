from __future__ import annotations

import logging
import sys
from pathlib import Path

from . import __version__
from .paths import PATHS, ensure_runtime_directories


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
    logging.getLogger(__name__).info(
        "Iniciando CinePulse %s; dados=%s; log=%s",
        __version__, PATHS.data, log_path,
    )
    from .studio import main as studio_main

    studio_main()

