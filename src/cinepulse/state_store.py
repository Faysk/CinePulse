"""Versioned queue/preset JSON persistence with migration and backup."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any


QUEUE_SCHEMA = 2
PRESETS_SCHEMA = 1


def _backup(path: Path) -> None:
    if not path.is_file():
        return
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        shutil.copy2(path, backup)
    except OSError:
        pass


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def save_queue_state(path: Path, items: list[dict]) -> None:
    _atomic_write(path, {
        "schema": QUEUE_SCHEMA,
        "kind": "cinepulse.queue",
        "updated_at": time.time(),
        "items": items,
    })


def load_queue_state(path: Path) -> tuple[list[dict], bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload, True
    if not isinstance(payload, dict) or payload.get("kind") != "cinepulse.queue":
        raise ValueError("Arquivo de fila não possui formato reconhecido.")
    schema = int(payload.get("schema") or 0)
    if schema > QUEUE_SCHEMA:
        raise ValueError(f"Fila usa schema futuro {schema}; esta versão suporta até {QUEUE_SCHEMA}.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Fila versionada não contém uma lista de items válida.")
    return items, schema != QUEUE_SCHEMA


def save_presets_state(path: Path, presets: dict[str, dict]) -> None:
    _atomic_write(path, {
        "schema": PRESETS_SCHEMA,
        "kind": "cinepulse.presets",
        "updated_at": time.time(),
        "items": presets,
    })


def load_presets_state(path: Path) -> tuple[dict[str, dict], bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and payload.get("kind") == "cinepulse.presets":
        schema = int(payload.get("schema") or 0)
        if schema > PRESETS_SCHEMA:
            raise ValueError(f"Presets usam schema futuro {schema}; esta versão suporta até {PRESETS_SCHEMA}.")
        items = payload.get("items")
        if not isinstance(items, dict):
            raise ValueError("Arquivo de presets versionado não contém objeto items válido.")
        return items, schema != PRESETS_SCHEMA
    if isinstance(payload, dict):
        # Legacy CinePulse stored presets directly at the JSON root.
        return payload, True
    raise ValueError("Arquivo de presets não possui formato reconhecido.")
