"""Persistent per-render technical history with Phase 1 durable manifest shadowing."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
import zipfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

from .job_store import JobStore
from .render_job import InvalidJobTransition, ManifestError, RenderJobManifest
from .hardware_telemetry import HardwareTelemetrySession


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


def _source_identity(settings: Any) -> dict[str, Any]:
    value = str(getattr(settings, "video", "") or "")
    identity: dict[str, Any] = {"path_hint": value}
    if not value:
        return identity
    path = Path(value)
    try:
        stat = path.stat()
    except OSError:
        return identity
    identity.update({"size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return identity


def _fingerprint(plan: Any) -> str:
    if isinstance(plan, dict):
        return str(plan.get("fingerprint") or "")
    return str(getattr(plan, "fingerprint", "") or "")


class RenderHistory:
    """Keep legacy history while shadow-writing the new durable manifest.

    Phase 1 is intentionally reversible: `job.json` remains the compatibility
    surface used by rc.6 while `manifest.json` becomes the transactional source
    of truth for the recovery architecture. Manifest failures are recorded but
    do not make the legacy history writer destroy an otherwise valid render.
    """

    def __init__(self, root: Path, job_id: str, job_dir: Path) -> None:
        self.root = root
        self.job_id = job_id
        self.job_dir = job_dir
        self.log_path = job_dir / "render.log"
        self.job_path = job_dir / "job.json"
        self.manifest_path = job_dir / "manifest.json"
        self.job_store = JobStore(self.manifest_path)
        self._telemetry: HardwareTelemetrySession | None = None

    @classmethod
    def start(cls, root: Path, settings: Any, *, preview: bool, app_version: str, queue_id: int | None = None) -> "RenderHistory":
        root.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        job_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
        job_dir = root / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        history = cls(root, job_id, job_dir)
        telemetry_error = ""
        try:
            history._telemetry = HardwareTelemetrySession(job_dir / "hardware-telemetry.json").start()
        except Exception as exc:
            history._telemetry = None
            telemetry_error = f"{type(exc).__name__}: {exc}"
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
        if telemetry_error:
            history.append_log(f"TELEMETRY WARNING start failed: {telemetry_error}")
        try:
            manifest = history.job_store.initialize(job_id, source=_source_identity(settings), begin_preflight=True)
            history.append_log(
                f"MANIFEST created schema={manifest.schema} revision={manifest.revision} state={manifest.state}"
            )
        except Exception as exc:
            history.append_log(f"MANIFEST WARNING start failed: {type(exc).__name__}: {exc}")
        return history

    def _job(self) -> dict:
        try:
            payload = json.loads(self.job_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _manifest_update(self, mutator: Callable[[RenderJobManifest], RenderJobManifest], label: str) -> RenderJobManifest | None:
        if not self.manifest_path.is_file():
            return None
        try:
            updated = self.job_store.update(mutator)
            self.append_log(f"MANIFEST {label} revision={updated.revision} state={updated.state}")
            return updated
        except Exception as exc:
            self.append_log(f"MANIFEST WARNING {label}: {type(exc).__name__}: {exc}")
            return None

    def _manifest_transition(self, target: str, reason: str) -> RenderJobManifest | None:
        if not self.manifest_path.is_file():
            return None
        try:
            current = self.job_store.load()
            if current.state == target:
                return current
            if target not in {"complete", "cancelled", "blocked"} and target not in {
                "preflight", "running", "verifying", "recoverable", "auditing", "repairing", "paused"
            }:
                return current
            updated = self.job_store.transition(target, reason=reason)
            self.append_log(f"MANIFEST transition {current.state}->{target} revision={updated.revision}")
            return updated
        except InvalidJobTransition as exc:
            self.append_log(f"MANIFEST WARNING transition {target}: {exc}")
            return None
        except Exception as exc:
            self.append_log(f"MANIFEST WARNING transition {target}: {type(exc).__name__}: {exc}")
            return None

    def append_log(self, message: str) -> None:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self.job_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"[{stamp}] {message}\n")
        telemetry = self._telemetry
        if telemetry is not None:
            match = re.match(r"^\[([^\]]+)\]\s*(.*)$", str(message))
            if match:
                try:
                    telemetry.mark_stage(match.group(1), match.group(2))
                except Exception:
                    pass

    def write_plan(self, plan: Any) -> Path:
        path = self.job_dir / "plan.json"
        _atomic_json(path, _jsonable(plan))
        fingerprint = _fingerprint(plan)
        if fingerprint:
            self._manifest_update(
                lambda current: current.with_render_plan(fingerprint, path=path.name),
                "render_plan",
            )
        try:
            current = self.job_store.load()
        except Exception:
            current = None
        if current is not None and current.state == "preflight":
            self._manifest_transition("running", "render_plan_ready")
        return path

    def write_contracts(self, **contracts: Any) -> Path:
        path = self.job_dir / "contracts.json"
        payload = {key: _jsonable(value) for key, value in contracts.items() if value is not None}
        _atomic_json(path, {"schema": 1, "job_id": self.job_id, **payload})
        expected = payload.get("verification_expected")
        if isinstance(expected, dict):
            self._manifest_update(
                lambda current: current.with_expectation(expected),
                "expectation",
            )
        return path

    def write_verification(self, verification: Any) -> Path:
        path = self.job_dir / "verification.json"
        _atomic_json(path, {"schema": 1, "job_id": self.job_id, "verification": _jsonable(verification)})
        try:
            current = self.job_store.load()
        except Exception:
            current = None
        if current is not None and current.state == "running":
            self._manifest_transition("verifying", "verification_started")
        return path

    def finish(self, status: str, *, output: str | Path | None = None, report: str | Path | None = None, error: str = "") -> None:
        hardware_summary: dict[str, Any] = {}
        telemetry = self._telemetry
        if telemetry is not None:
            try:
                telemetry_payload = telemetry.stop(status=status)
                if isinstance(telemetry_payload, dict) and isinstance(telemetry_payload.get("summary"), dict):
                    hardware_summary = telemetry_payload["summary"]
            except Exception as exc:
                self.append_log(f"TELEMETRY WARNING stop failed: {type(exc).__name__}: {exc}")
            finally:
                self._telemetry = None
        payload = self._job()
        payload.update({
            "schema": HISTORY_SCHEMA,
            "job_id": self.job_id,
            "status": status,
            "finished_at": time.time(),
            "output": str(output or payload.get("output") or ""),
            "report": str(report or ""),
            "error": str(error or ""),
            "hardware_telemetry": "hardware-telemetry.json" if (self.job_dir / "hardware-telemetry.json").is_file() else "",
            "hardware_summary": hardware_summary,
        })
        _atomic_json(self.job_path, payload)

        if self.manifest_path.is_file():
            try:
                current = self.job_store.load()
            except Exception:
                current = None
            if current is not None:
                if status == "success":
                    if current.state == "running":
                        self._manifest_transition("verifying", "legacy_finish_verification")
                        try:
                            current = self.job_store.load()
                        except Exception:
                            current = None
                    if current is not None and current.state == "verifying":
                        self._manifest_transition("complete", "verification_approved")
                elif status == "cancelled":
                    if current.state in {"preflight", "running", "paused", "recoverable", "blocked"}:
                        self._manifest_transition("cancelled", "user_cancelled")
                elif status == "error":
                    self._manifest_update(
                        lambda manifest: manifest.with_error(
                            code="RENDER-ERROR",
                            message=str(error or "render failed"),
                            retryable=True,
                        ),
                        "error",
                    )
                    try:
                        current = self.job_store.load()
                    except Exception:
                        current = None
                    if current is not None and current.state in {"preflight", "running", "verifying"}:
                        self._manifest_transition("blocked", "render_error")

        self.append_log(f"HISTORY finished status={status} output={payload['output'] or '-'} report={payload['report'] or '-'}")

    @property
    def path(self) -> str:
        return str(self.job_dir)


def _redact_text(text: str) -> str:
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
