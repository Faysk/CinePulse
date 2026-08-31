from __future__ import annotations

import copy
import time
from dataclasses import dataclass, replace
from typing import Any, Mapping


RENDER_JOB_SCHEMA = 1
RENDER_JOB_KIND = "cinepulse.render-job"

JOB_STATES = (
    "queued",
    "preflight",
    "running",
    "pause_requested",
    "paused",
    "interrupted",
    "auditing",
    "repairing",
    "recoverable",
    "blocked",
    "verifying",
    "complete",
    "cancelled",
    "discarded",
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"preflight"}),
    "preflight": frozenset({"running", "blocked", "cancelled"}),
    "running": frozenset({"pause_requested", "verifying", "interrupted", "recoverable", "blocked", "cancelled"}),
    "pause_requested": frozenset({"paused", "interrupted", "blocked"}),
    "paused": frozenset({"recoverable", "cancelled"}),
    "interrupted": frozenset({"auditing"}),
    "auditing": frozenset({"recoverable", "repairing", "blocked"}),
    "repairing": frozenset({"auditing", "recoverable", "blocked"}),
    "recoverable": frozenset({"preflight", "cancelled"}),
    "blocked": frozenset({"auditing", "recoverable", "cancelled"}),
    "verifying": frozenset({"complete", "recoverable", "blocked"}),
    "complete": frozenset({"discarded"}),
    "cancelled": frozenset({"recoverable", "discarded"}),
    "discarded": frozenset(),
}


class ManifestError(RuntimeError):
    pass


class UnsupportedManifestSchema(ManifestError):
    pass


class InvalidJobTransition(ManifestError):
    pass


def _copy_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(dict(value or {}))


@dataclass(frozen=True)
class RenderJobManifest:
    job_id: str
    revision: int
    created_at: float
    updated_at: float
    state: str
    reason: str
    render_plan: dict[str, Any]
    source: dict[str, Any]
    attempt: dict[str, Any]
    phase: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    expectation: dict[str, Any]
    last_error: dict[str, Any] | None
    cleanup: dict[str, Any]
    schema: int = RENDER_JOB_SCHEMA
    kind: str = RENDER_JOB_KIND

    @classmethod
    def new(
        cls,
        job_id: str,
        *,
        source: Mapping[str, Any] | None = None,
        now: float | None = None,
    ) -> "RenderJobManifest":
        stamp = float(time.time() if now is None else now)
        if not job_id:
            raise ManifestError("job_id não pode ser vazio")
        return cls(
            job_id=job_id,
            revision=0,
            created_at=stamp,
            updated_at=stamp,
            state="queued",
            reason="created",
            render_plan={"fingerprint": "", "path": "plan.json"},
            source=_copy_mapping(source),
            attempt={},
            phase={"name": "queued", "status": "queued", "units_total": None, "units_committed": 0},
            artifacts=(),
            expectation={},
            last_error=None,
            cleanup={"eligible": False, "accepted_at": None},
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RenderJobManifest":
        schema = int(payload.get("schema") or 0)
        if schema > RENDER_JOB_SCHEMA:
            raise UnsupportedManifestSchema(
                f"manifest schema futuro {schema}; suportado até {RENDER_JOB_SCHEMA}"
            )
        if schema != RENDER_JOB_SCHEMA or payload.get("kind") != RENDER_JOB_KIND:
            raise ManifestError("manifesto de render possui schema/kind inválido")
        state = str(payload.get("state") or "")
        if state not in JOB_STATES:
            raise ManifestError(f"estado de job desconhecido: {state!r}")
        job_id = str(payload.get("job_id") or "")
        if not job_id:
            raise ManifestError("manifesto não possui job_id")
        try:
            revision = int(payload.get("revision"))
            created_at = float(payload.get("created_at"))
            updated_at = float(payload.get("updated_at"))
        except (TypeError, ValueError) as exc:
            raise ManifestError("revision/created_at/updated_at inválidos") from exc
        artifacts_raw = payload.get("artifacts") or []
        if not isinstance(artifacts_raw, list):
            raise ManifestError("artifacts deve ser uma lista")
        last_error = payload.get("last_error")
        if last_error is not None and not isinstance(last_error, Mapping):
            raise ManifestError("last_error deve ser objeto ou null")
        return cls(
            schema=schema,
            kind=RENDER_JOB_KIND,
            job_id=job_id,
            revision=revision,
            created_at=created_at,
            updated_at=updated_at,
            state=state,
            reason=str(payload.get("reason") or ""),
            render_plan=_copy_mapping(payload.get("render_plan") if isinstance(payload.get("render_plan"), Mapping) else {}),
            source=_copy_mapping(payload.get("source") if isinstance(payload.get("source"), Mapping) else {}),
            attempt=_copy_mapping(payload.get("attempt") if isinstance(payload.get("attempt"), Mapping) else {}),
            phase=_copy_mapping(payload.get("phase") if isinstance(payload.get("phase"), Mapping) else {}),
            artifacts=tuple(_copy_mapping(item) for item in artifacts_raw if isinstance(item, Mapping)),
            expectation=_copy_mapping(payload.get("expectation") if isinstance(payload.get("expectation"), Mapping) else {}),
            last_error=_copy_mapping(last_error) if isinstance(last_error, Mapping) else None,
            cleanup=_copy_mapping(payload.get("cleanup") if isinstance(payload.get("cleanup"), Mapping) else {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "kind": self.kind,
            "job_id": self.job_id,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state": self.state,
            "reason": self.reason,
            "render_plan": copy.deepcopy(self.render_plan),
            "source": copy.deepcopy(self.source),
            "attempt": copy.deepcopy(self.attempt),
            "phase": copy.deepcopy(self.phase),
            "artifacts": [copy.deepcopy(item) for item in self.artifacts],
            "expectation": copy.deepcopy(self.expectation),
            "last_error": copy.deepcopy(self.last_error),
            "cleanup": copy.deepcopy(self.cleanup),
        }

    def _mutate(self, *, now: float | None = None, **changes: Any) -> "RenderJobManifest":
        stamp = float(time.time() if now is None else now)
        return replace(self, revision=self.revision + 1, updated_at=stamp, **changes)

    def transition(self, target: str, *, reason: str = "", now: float | None = None) -> "RenderJobManifest":
        if target not in JOB_STATES:
            raise InvalidJobTransition(f"estado de destino desconhecido: {target}")
        if target == self.state:
            raise InvalidJobTransition(f"job já está em {target}")
        if target not in ALLOWED_TRANSITIONS[self.state]:
            raise InvalidJobTransition(f"transição inválida: {self.state} -> {target}")
        phase = copy.deepcopy(self.phase)
        phase["status"] = target
        if target in {"preflight", "running", "auditing", "repairing", "verifying"}:
            phase["name"] = target
        return self._mutate(state=target, reason=reason or target, phase=phase, now=now)

    def with_render_plan(self, fingerprint: str, *, path: str = "plan.json", now: float | None = None) -> "RenderJobManifest":
        if not fingerprint:
            raise ManifestError("fingerprint do RenderPlan não pode ser vazio")
        return self._mutate(
            render_plan={"fingerprint": str(fingerprint), "path": str(path)},
            reason="render_plan_recorded",
            now=now,
        )

    def with_expectation(self, expectation: Mapping[str, Any], *, now: float | None = None) -> "RenderJobManifest":
        return self._mutate(expectation=_copy_mapping(expectation), reason="expectation_recorded", now=now)

    def with_phase_progress(
        self,
        *,
        name: str,
        units_total: int | None,
        units_committed: int,
        unit_kind: str = "units",
        last_commit: str | None = None,
        now: float | None = None,
    ) -> "RenderJobManifest":
        if units_committed < 0 or (units_total is not None and units_committed > units_total):
            raise ManifestError("progresso de fase inválido")
        phase = {
            "name": str(name),
            "status": self.state,
            "units_total": units_total,
            "units_committed": int(units_committed),
            "unit_kind": str(unit_kind),
            "last_commit": last_commit,
        }
        return self._mutate(phase=phase, reason="phase_progress", now=now)

    def with_error(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        artifact_id: str | None = None,
        now: float | None = None,
    ) -> "RenderJobManifest":
        error = {
            "code": str(code),
            "message": str(message),
            "retryable": bool(retryable),
            "artifact_id": artifact_id,
        }
        return self._mutate(last_error=error, reason=code, now=now)
