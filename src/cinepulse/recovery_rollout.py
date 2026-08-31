from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RecoveryFlags:
    ring: int = 1
    recovery_manifest_write: bool = True
    recovery_worker: bool = False
    recovery_discovery: bool = False
    recovery_stage_adapters: bool = False
    recovery_cleanup_ui: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


RINGS: dict[int, RecoveryFlags] = {
    0: RecoveryFlags(ring=0, recovery_manifest_write=False),
    1: RecoveryFlags(ring=1, recovery_manifest_write=True),
    2: RecoveryFlags(ring=2, recovery_manifest_write=True, recovery_worker=True, recovery_stage_adapters=True),
    3: RecoveryFlags(ring=3, recovery_manifest_write=True, recovery_worker=True, recovery_discovery=True, recovery_stage_adapters=True),
    4: RecoveryFlags(ring=4, recovery_manifest_write=True, recovery_worker=True, recovery_discovery=True, recovery_stage_adapters=True),
    5: RecoveryFlags(ring=5, recovery_manifest_write=True, recovery_worker=True, recovery_discovery=True, recovery_stage_adapters=True, recovery_cleanup_ui=True),
}


def _bool(value: object) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def flags_for_ring(ring: int) -> RecoveryFlags:
    if ring not in RINGS:
        raise ValueError(f"recovery rollout ring inválido: {ring}")
    return RINGS[ring]


def load_recovery_flags(path: Path | None = None) -> RecoveryFlags:
    flags = RecoveryFlags()
    if path is not None and path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("recovery flags deve ser objeto JSON")
        ring = int(payload.get("ring", flags.ring))
        baseline = flags_for_ring(ring)
        values = baseline.to_dict()
        for key in values:
            if key == "ring":
                continue
            if key in payload:
                values[key] = bool(payload[key])
        flags = RecoveryFlags(**values)
    env_ring = os.environ.get("CINEPULSE_RECOVERY_RING")
    if env_ring is not None:
        flags = flags_for_ring(int(env_ring))
    values = flags.to_dict()
    for key in list(values):
        if key == "ring":
            continue
        env_name = "CINEPULSE_" + key.upper()
        if env_name in os.environ:
            values[key] = _bool(os.environ[env_name])
    return RecoveryFlags(**values)


def write_ring(path: Path, ring: int) -> RecoveryFlags:
    flags = flags_for_ring(ring)
    _atomic_json(path, flags.to_dict())
    return flags


def rollback_to_shadow(path: Path) -> RecoveryFlags:
    """Disable execution/discovery without touching any manifest or artifact."""
    flags = flags_for_ring(1)
    _atomic_json(path, flags.to_dict())
    return flags
