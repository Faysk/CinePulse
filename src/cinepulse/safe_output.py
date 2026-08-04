from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AtomicOutput:
    final: Path
    partial: Path
    backup: Path

    @classmethod
    def for_path(cls, final: Path, pid: int | None = None) -> "AtomicOutput":
        final = final.expanduser().resolve()
        process_id = pid if pid is not None else os.getpid()
        partial = final.with_name(f".{final.stem}.partial-{process_id}{final.suffix}")
        backup = final.with_name(f".{final.name}.previous")
        return cls(final=final, partial=partial, backup=backup)

    def prepare(self) -> Path:
        self.final.parent.mkdir(parents=True, exist_ok=True)
        self.partial.unlink(missing_ok=True)
        return self.partial

    def commit(self) -> Path:
        if not self.partial.is_file() or self.partial.stat().st_size == 0:
            raise RuntimeError("A saída temporária não existe ou está vazia.")
        self.backup.unlink(missing_ok=True)
        had_previous = self.final.exists()
        if had_previous:
            os.replace(self.final, self.backup)
        try:
            os.replace(self.partial, self.final)
        except Exception:
            if had_previous and self.backup.exists() and not self.final.exists():
                os.replace(self.backup, self.final)
            raise
        self.backup.unlink(missing_ok=True)
        return self.final

    def discard(self) -> None:
        self.partial.unlink(missing_ok=True)


class RenderJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, atomic: AtomicOutput, preview: bool, expected: dict | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        payload = {
            "schema": 1,
            "pid": os.getpid(),
            "started_at": time.time(),
            "preview": bool(preview),
            "final": str(atomic.final),
            "partial": str(atomic.partial),
            "expected": expected or {},
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    def read(self) -> dict | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return payload if payload.get("schema") == 1 else None

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False

