"""Versioned queue/preset JSON persistence with migration and backup recovery."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, TypeVar


QUEUE_SCHEMA = 2
PRESETS_SCHEMA = 1
_T = TypeVar("_T")


class StateSchemaTooNew(ValueError):
    """A state file belongs to a newer CinePulse and must not be downgraded."""


def _backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".bak")


def _backup(path: Path) -> None:
    if not path.is_file():
        return
    backup = _backup_path(path)
    try:
        shutil.copy2(path, backup)
    except OSError:
        pass


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".restore.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _queue_from_payload(payload: Any) -> tuple[list[dict], bool]:
    if isinstance(payload, list):
        return payload, True
    if not isinstance(payload, dict) or payload.get("kind") != "cinepulse.queue":
        raise ValueError("Arquivo de fila não possui formato reconhecido.")
    schema = int(payload.get("schema") or 0)
    if schema > QUEUE_SCHEMA:
        raise StateSchemaTooNew(f"Fila usa schema futuro {schema}; esta versão suporta até {QUEUE_SCHEMA}.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Fila versionada não contém uma lista de items válida.")
    return items, schema != QUEUE_SCHEMA


def _presets_from_payload(payload: Any) -> tuple[dict[str, dict], bool]:
    if isinstance(payload, dict) and payload.get("kind") == "cinepulse.presets":
        schema = int(payload.get("schema") or 0)
        if schema > PRESETS_SCHEMA:
            raise StateSchemaTooNew(f"Presets usam schema futuro {schema}; esta versão suporta até {PRESETS_SCHEMA}.")
        items = payload.get("items")
        if not isinstance(items, dict):
            raise ValueError("Arquivo de presets versionado não contém objeto items válido.")
        return items, schema != PRESETS_SCHEMA
    if isinstance(payload, dict):
        return payload, True
    raise ValueError("Arquivo de presets não possui formato reconhecido.")


def _read_and_parse(path: Path, parser: Callable[[Any], _T]) -> _T:
    return parser(json.loads(path.read_text(encoding="utf-8")))


def _load_with_backup(path: Path, parser: Callable[[Any], _T]) -> tuple[_T, bool]:
    """Load primary state and recover corruption from a validated `.bak`.

    A future schema is intentionally *not* recovered from an older backup: that
    would silently downgrade and potentially discard state written by a newer
    CinePulse. Backup recovery is only for unreadable/invalid current state.
    """
    try:
        return _read_and_parse(path, parser), False
    except StateSchemaTooNew:
        raise
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as primary_error:
        backup = _backup_path(path)
        if not backup.is_file():
            raise primary_error
        try:
            parsed = _read_and_parse(backup, parser)
        except StateSchemaTooNew:
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as backup_error:
            raise ValueError(
                f"Estado principal e backup estão inválidos: primary={primary_error}; backup={backup_error}"
            ) from backup_error
        if path.exists():
            evidence = path.with_name(f"{path.name}.corrupt-{int(time.time())}")
            try:
                os.replace(path, evidence)
            except OSError:
                pass
        _atomic_bytes(path, backup.read_bytes())
        return parsed, True


def save_queue_state(path: Path, items: list[dict]) -> None:
    _atomic_write(path, {
        "schema": QUEUE_SCHEMA,
        "kind": "cinepulse.queue",
        "updated_at": time.time(),
        "items": items,
    })


def load_queue_state(path: Path) -> tuple[list[dict], bool]:
    (items, migrated), recovered = _load_with_backup(path, _queue_from_payload)
    return items, bool(migrated or recovered)


def save_presets_state(path: Path, presets: dict[str, dict]) -> None:
    _atomic_write(path, {
        "schema": PRESETS_SCHEMA,
        "kind": "cinepulse.presets",
        "updated_at": time.time(),
        "items": presets,
    })


def load_presets_state(path: Path) -> tuple[dict[str, dict], bool]:
    (items, migrated), recovered = _load_with_backup(path, _presets_from_payload)
    return items, bool(migrated or recovered)
