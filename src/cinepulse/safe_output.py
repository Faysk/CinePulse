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
        # final and partial intentionally live in the same directory/filesystem.
        # os.replace(partial, final) therefore provides the atomic hand-off we
        # need while leaving an existing final untouched until the last step.
        # The old two-step final->backup, partial->final sequence had a crash
        # window in which the user's valid output disappeared from final.
        self.backup.unlink(missing_ok=True)
        os.replace(self.partial, self.final)
        return self.final

    def discard(self, *, timeout_seconds: float = 5.0, retry_seconds: float = 0.05) -> None:
        """Remove an abandoned partial, tolerating only transient Windows locks.

        ``taskkill /T /F`` can return just before a terminated FFmpeg descendant
        releases its output handle. Windows then raises ``PermissionError`` even
        though cancellation itself succeeded. Retry that one condition for a
        bounded interval; a persistent lock still propagates so recovery never
        pretends cleanup worked.
        """
        deadline = time.monotonic() + max(0.0, float(timeout_seconds))
        delay = max(0.001, float(retry_seconds))
        while True:
            try:
                self.partial.unlink(missing_ok=True)
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(delay)


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
    except PermissionError:
        # EPERM means the process exists but belongs to a security context the
        # current process cannot signal. Treating it as dead can steal locks.
        return True
    except OSError:
        return False
