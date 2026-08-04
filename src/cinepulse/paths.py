from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


APP_NAME = "CinePulse"
PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_ROOT = PACKAGE_DIR.parent.parent


def _executable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT


def _data_root() -> Path:
    override = os.environ.get("CINEPULSE_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    executable_root = _executable_root()
    if os.environ.get("CINEPULSE_PORTABLE") == "1" or (executable_root / ".cinepulse-portable").exists():
        return executable_root / "data"
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / APP_NAME


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    data: Path
    config: Path
    cache: Path
    temp: Path
    previews: Path
    work: Path
    reports: Path
    logs: Path
    components: Path
    models: Path
    locks: Path


_root = _executable_root()
_data = _data_root()
_component_override = os.environ.get("CINEPULSE_COMPONENTS_DIR")
_components = Path(_component_override).expanduser().resolve() if _component_override else _root / "components"
PATHS = RuntimePaths(
    root=_root,
    data=_data,
    config=_data / "config",
    cache=_data / "cache",
    temp=_data / "temp",
    previews=_data / "temp" / "previews",
    work=_data / "temp" / "work",
    reports=_data / "reports",
    logs=_data / "logs",
    components=_components,
    models=_components / "models",
    locks=_data / "locks",
)


def ensure_runtime_directories() -> None:
    for directory in (
        PATHS.config, PATHS.cache, PATHS.previews, PATHS.work,
        PATHS.reports, PATHS.logs, PATHS.components, PATHS.models, PATHS.locks,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def component_path(relative_path: str) -> Path:
    """Prefer the isolated component store, with read-only legacy discovery during migration."""
    managed = PATHS.components / relative_path
    legacy = PATHS.root.parent / "tools" / relative_path
    if managed.exists() or not legacy.exists():
        return managed
    return legacy
