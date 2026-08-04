from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .ai_suite import inventory
from .paths import PATHS, ensure_runtime_directories
from .integrity import verify as verify_integrity


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=8,
            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
        )
        line = (result.stdout or result.stderr).splitlines()
        return line[0].strip() if line else None
    except (OSError, subprocess.SubprocessError):
        return None


def collect() -> dict:
    ensure_runtime_directories()
    disk = shutil.disk_usage(PATHS.data)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    return {
        "cinepulse": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_threads": os.cpu_count(),
        "paths": {
            "data": str(PATHS.data),
            "components": str(PATHS.components),
        },
        "disk": {
            "free_gb": round(disk.free / 1024**3, 2),
            "total_gb": round(disk.total / 1024**3, 2),
        },
        "tools": {
            "ffmpeg": _version([ffmpeg, "-version"]) if ffmpeg else None,
            "ffprobe": _version([ffprobe, "-version"]) if ffprobe else None,
            "nvidia": _version(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
        },
        "ai": inventory(),
        "integrity": verify_integrity(),
    }


def write_report(destination: Path | None = None) -> Path:
    ensure_runtime_directories()
    path = destination or PATHS.reports / "diagnostico-cinepulse.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(collect(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    print(write_report())
