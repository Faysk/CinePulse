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


def _path_override(name: str, fallback: Path) -> Path:
    override = os.environ.get(name)
    if override:
        return Path(override).expanduser().resolve()
    return fallback.resolve()


def _data_root() -> Path:
    """CinePulse 1.1+ is self-contained by default.

    Installed and portable builds keep mutable application data under the chosen
    CinePulse root.  A caller may still override the location explicitly for
    development/tests, but there is no implicit %LOCALAPPDATA% fallback.
    """
    root = _executable_root()
    return _path_override("CINEPULSE_DATA_DIR", root / "data")


def _cache_root() -> Path:
    root = _executable_root()
    return _path_override("CINEPULSE_CACHE_DIR", root / "cache")


def _temp_root() -> Path:
    root = _executable_root()
    return _path_override("CINEPULSE_TEMP_DIR", root / "temp")


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
_cache = _cache_root()
_temp = _temp_root()
_component_override = os.environ.get("CINEPULSE_COMPONENTS_DIR")
_components = Path(_component_override).expanduser().resolve() if _component_override else (_root / "components").resolve()
PATHS = RuntimePaths(
    root=_root,
    data=_data,
    config=_data / "config",
    cache=_cache,
    temp=_temp,
    previews=_temp / "previews",
    work=_temp / "work",
    reports=_data / "reports",
    logs=_data / "logs",
    components=_components,
    models=_components / "models",
    locks=_data / "locks",
)


def ensure_runtime_directories() -> None:
    for directory in (
        PATHS.data,
        PATHS.config,
        PATHS.cache,
        PATHS.temp,
        PATHS.previews,
        PATHS.work,
        PATHS.reports,
        PATHS.logs,
        PATHS.components,
        PATHS.models,
        PATHS.locks,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def component_path(relative_path: str) -> Path:
    """Prefer the isolated component store, with read-only legacy discovery during migration."""
    managed = PATHS.components / relative_path
    legacy = PATHS.root.parent / "tools" / relative_path
    if managed.exists() or not legacy.exists():
        return managed
    return legacy
