"""Persistent per-render technical history for CinePulse Core Integrity Phase 7."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


HISTORY_SCHEMA = 1


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(temporary, path)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _settings_payload(settings: Any) -> dict:
    raw = asdict(settings) if is_dataclass(settings) else dict(settings)
    raw["effects"] = sorted(raw.get("effects", []))
    return _jsonable(raw)


class RenderHistory:
    def __init__(self, root: Path, job_id: str, job_dir: Path) -> None:
        self.root = root
        self.job_id = job_id
        self.job_dir = job_dir
        self.log_path = job_dir / "render.log"
        self.job_path = job_dir / "job.json"

    @classmethod
    def start(cls, root: Path, settings: Any, *, preview: bool, app_version: str, queue_id: int | None = None) -> "RenderHistory":
        root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        job_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
        job_dir = root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        history = cls(root, job_id, job_dir)
        now = time.time()
        _atomic_json(history.job_path, {
            "schema": HISTORY_SCHEMA,
            "job_id": job_id,
            "status": "running",
            "preview": bool(preview),
            "queue_id": queue_id,
            "app_version": app_version,
            "started_at": now,
            "finished_at": None,
            "output": str(getattr(settings, "output", "") or ""),
            "report": "",
            "error": "",
            "settings": _settings_payload(settings),
        })
        history.append_log(f"HISTORY job_id={job_id} schema={HISTORY_SCHEMA} preview={bool(preview)}")
        return history

    def _job(self) -> dict:
        try:
            payload = json.loads(self.job_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def append_log(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.job_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"[{stamp}] {message}\n")

    def write_plan(self, plan: Any) -> Path:
        path = self.job_dir / "plan.json"
        _atomic_json(path, _jsonable(plan))
        return path

    def write_contracts(self, **contracts: Any) -> Path:
        path = self.job_dir / "contracts.json"
        payload = {key: _jsonable(value) for key, value in contracts.items() if value is not None}
        _atomic_json(path, {"schema": 1, "job_id": self.job_id, **payload})
        return path

    def write_verification(self, verification: Any) -> Path:
        path = self.job_dir / "verification.json"
        _atomic_json(path, {"schema": 1, "job_id": self.job_id, "verification": _jsonable(verification)})
        return path

    def finish(self, status: str, *, output: str | Path | None = None, report: str | Path | None = None, error: str = "") -> None:
        payload = self._job()
        payload.update({
            "schema": HISTORY_SCHEMA,
            "job_id": self.job_id,
            "status": status,
            "finished_at": time.time(),
            "output": str(output or payload.get("output") or ""),
            "report": str(report or ""),
            "error": str(error or ""),
        })
        _atomic_json(self.job_path, payload)
        self.append_log(f"HISTORY finished status={status} output={payload['output'] or '-'} report={payload['report'] or '-'}")

    @property
    def path(self) -> str:
        return str(self.job_dir)


def _redact_text(text: str) -> str:
    # Redact Windows drive paths and absolute POSIX paths while preserving the
    # basename so support can still reason about extensions/artifact names.
    windows = re.compile(r"(?i)(?:[A-Z]:\\(?:[^\s\"'|]+\\)*)([^\\\s\"'|]+)")
    text = windows.sub(lambda match: f"<PATH>\\{match.group(1)}", text)
    posix = re.compile(r"(?<![\w.])/(?:[^\s\"'|/]+/)+([^/\s\"'|]+)")
    return posix.sub(lambda match: f"<PATH>/{match.group(1)}", text)


def export_redacted_history(job_dir: Path, destination_zip: Path) -> Path:
    """Create a support bundle with local paths redacted from text/JSON files."""
    job_dir = job_dir.resolve()
    destination_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(job_dir.iterdir()):
            if not source.is_file():
                continue
            if source.suffix.lower() in {".json", ".log", ".txt", ".md"}:
                redacted = _redact_text(source.read_text(encoding="utf-8", errors="replace"))
                archive.writestr(source.name, redacted)
            else:
                archive.write(source, source.name)
    return destination_zip
