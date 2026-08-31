from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


CHECKPOINT_SCHEMA = 1
UNIT_STATES = frozenset({"planned", "producing", "validating", "committed", "rejected", "quarantined", "interrupted"})


class CheckpointError(RuntimeError):
    pass


@dataclass(frozen=True)
class UnitRecord:
    unit_id: str
    ordinal: int
    state: str
    artifact: str
    contract: dict
    validation: dict
    updated_at: float

    def to_dict(self) -> dict:
        return asdict(self)


class StageCheckpointStore:
    def __init__(self, path: Path, *, job_id: str, attempt_id: str, stage: str, policy_fingerprint: str) -> None:
        self.path = Path(path)
        self.job_id = job_id
        self.attempt_id = attempt_id
        self.stage = stage
        self.policy_fingerprint = policy_fingerprint

    def _empty(self) -> dict:
        return {
            "schema": CHECKPOINT_SCHEMA,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "stage": self.stage,
            "policy_fingerprint": self.policy_fingerprint,
            "revision": 0,
            "updated_at": time.time(),
            "units": {},
        }

    def load(self) -> dict:
        if not self.path.is_file():
            return self._empty()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CheckpointError(f"checkpoint ilegível: {exc}") from exc
        if not isinstance(payload, dict) or int(payload.get("schema") or 0) != CHECKPOINT_SCHEMA:
            raise CheckpointError("checkpoint schema inválido")
        for field, expected in (
            ("job_id", self.job_id),
            ("attempt_id", self.attempt_id),
            ("stage", self.stage),
            ("policy_fingerprint", self.policy_fingerprint),
        ):
            if str(payload.get(field) or "") != expected:
                raise CheckpointError(f"checkpoint {field} diverge do contrato")
        if not isinstance(payload.get("units"), dict):
            raise CheckpointError("checkpoint units inválido")
        return payload

    def _write(self, payload: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp-{uuid.uuid4().hex}")
        payload = dict(payload)
        payload["revision"] = int(payload.get("revision") or 0) + 1
        payload["updated_at"] = time.time()
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        return payload

    def record(
        self,
        *,
        unit_id: str,
        ordinal: int,
        state: str,
        artifact: str,
        contract: dict | None = None,
        validation: dict | None = None,
    ) -> dict:
        if state not in UNIT_STATES:
            raise CheckpointError(f"estado de unidade inválido: {state}")
        payload = self.load()
        current = payload["units"].get(unit_id)
        # `producing -> producing` and `validating -> producing` are deliberate
        # recovery transitions. A real process crash can happen after the
        # durable state change but before Python gets a chance to record
        # `interrupted`. The next owner may safely restart that same unit because
        # the job lease prevents concurrent producers and any old partial stays
        # as evidence. At worst we redo the current unit; committed work is never
        # invalidated.
        allowed = {
            None: {"planned", "producing", "committed"},
            "planned": {"producing", "interrupted", "quarantined"},
            "producing": {"producing", "validating", "interrupted", "rejected"},
            "validating": {"producing", "committed", "rejected", "interrupted"},
            "interrupted": {"planned", "producing", "quarantined", "committed"},
            "rejected": {"quarantined", "producing"},
            "quarantined": {"producing"},
            "committed": {"committed"},
        }
        old_state = current.get("state") if isinstance(current, dict) else None
        if state not in allowed.get(old_state, set()):
            raise CheckpointError(f"transição de unidade inválida: {old_state} -> {state}")
        payload["units"][unit_id] = UnitRecord(
            unit_id=unit_id,
            ordinal=int(ordinal),
            state=state,
            artifact=str(artifact),
            contract=dict(contract or (current.get("contract") if isinstance(current, dict) else {}) or {}),
            validation=dict(validation or (current.get("validation") if isinstance(current, dict) else {}) or {}),
            updated_at=time.time(),
        ).to_dict()
        return self._write(payload)

    def committed(self, unit_id: str) -> dict | None:
        unit = self.load()["units"].get(unit_id)
        if isinstance(unit, dict) and unit.get("state") == "committed":
            return unit
        return None

    def committed_count(self) -> int:
        return sum(1 for unit in self.load()["units"].values() if unit.get("state") == "committed")
