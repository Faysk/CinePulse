from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .job_lease import JobLease, LeaseError
from .job_store import JobStore


TERMINAL_STATES = frozenset({"complete", "discarded"})


@dataclass(frozen=True)
class RecoveryCandidate:
    job_id: str
    history_dir: str
    state: str
    classification: str
    reason: str
    phase: str
    units_committed: int
    units_total: int | None
    source_hint: str
    source_present: bool
    updated_at: float
    owner_pid: int | None
    owner_active: bool
    actions: tuple[str, ...]
    origin: str = "Recuperado do disco"

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["actions"] = list(self.actions)
        return payload

    def queue_payload(self) -> dict:
        return {
            "recovery_job_id": self.job_id,
            "recovery_origin": "history",
            "origin": self.origin,
            "status": self.classification,
            "phase": self.phase,
            "progress_committed": self.units_committed,
            "progress_total": self.units_total,
            "message": self.reason,
            "history_dir": self.history_dir,
            "recovery_actions": list(self.actions),
        }


class RecoveryService:
    def __init__(self, history_root: Path) -> None:
        self.history_root = Path(history_root)

    @staticmethod
    def _source(manifest) -> tuple[str, bool]:
        hint = str(manifest.source.get("path_hint") or "")
        if not hint:
            return "", True
        try:
            return hint, Path(hint).is_file()
        except OSError:
            return hint, False

    @staticmethod
    def _classification(manifest, *, owner_active: bool, source_present: bool, had_stale_lease: bool) -> tuple[str, str, tuple[str, ...]]:
        if owner_active:
            return "active", "Worker continua processando este job.", ("acompanhar", "pausar")
        if not source_present:
            return "blocked", "A fonte do job não está disponível.", ("inspecionar", "reconectar_fonte", "preservar")
        if manifest.state == "blocked":
            message = str((manifest.last_error or {}).get("message") or manifest.reason or "Ação necessária antes de continuar.")
            return "blocked", message, ("inspecionar", "preservar")
        if manifest.state in {"interrupted", "auditing", "repairing", "running"} or had_stale_lease:
            return "needs_audit", "Trabalho preservado encontrado; integridade deve ser conferida antes da retomada.", ("inspecionar", "auditar", "preservar")
        if manifest.state in {"paused", "recoverable", "cancelled"}:
            return "recoverable", "Checkpoint consistente disponível para retomada segura.", ("inspecionar", "retomar", "preservar")
        if manifest.state in {"queued", "preflight"}:
            return "recoverable", "Job persistido pode ser retomado pelo preflight.", ("inspecionar", "retomar", "preservar")
        if manifest.state == "verifying":
            return "needs_audit", "Entrega existe, mas ainda precisa concluir a verificação.", ("inspecionar", "verificar", "preservar")
        return "blocked", f"Estado {manifest.state} exige inspeção.", ("inspecionar", "preservar")

    def inspect_job(self, job_dir: Path) -> RecoveryCandidate | None:
        store = JobStore(job_dir / "manifest.json")
        manifest = store.load(recover_backup=True)
        if manifest.state in TERMINAL_STATES:
            return None
        lease = JobLease(job_dir / "lease.json", manifest.job_id)
        owner_pid: int | None = None
        owner_active = False
        had_stale_lease = False
        try:
            record = lease.read()
        except LeaseError:
            record = None
            had_stale_lease = True
        if record is not None:
            owner_pid = record.pid
            try:
                stale = lease.is_stale(record)
            except Exception:
                stale = False
            owner_active = not stale
            had_stale_lease = stale
        source_hint, source_present = self._source(manifest)
        classification, reason, actions = self._classification(
            manifest,
            owner_active=owner_active,
            source_present=source_present,
            had_stale_lease=had_stale_lease,
        )
        phase = str(manifest.phase.get("name") or manifest.state)
        committed = int(manifest.phase.get("units_committed") or 0)
        total_raw = manifest.phase.get("units_total")
        total = int(total_raw) if total_raw is not None else None
        return RecoveryCandidate(
            job_id=manifest.job_id,
            history_dir=str(job_dir),
            state=manifest.state,
            classification=classification,
            reason=reason,
            phase=phase,
            units_committed=committed,
            units_total=total,
            source_hint=source_hint,
            source_present=source_present,
            updated_at=manifest.updated_at,
            owner_pid=owner_pid,
            owner_active=owner_active,
            actions=actions,
        )

    def discover(self) -> list[RecoveryCandidate]:
        if not self.history_root.is_dir():
            return []
        candidates: list[RecoveryCandidate] = []
        for manifest_path in sorted(self.history_root.glob("*/manifest.json")):
            try:
                candidate = self.inspect_job(manifest_path.parent)
            except Exception:
                continue
            if candidate is not None:
                candidates.append(candidate)
        return sorted(candidates, key=lambda item: item.updated_at, reverse=True)

    def write_snapshot(self, destination: Path) -> Path:
        payload = {
            "schema": 1,
            "generated_at": time.time(),
            "history_root": str(self.history_root),
            "candidates": [candidate.to_dict() for candidate in self.discover()],
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return destination
