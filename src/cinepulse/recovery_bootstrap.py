from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .recovery_rollout import RecoveryFlags, load_recovery_flags
from .recovery_service import RecoveryService


@dataclass(frozen=True)
class RecoveryBootstrapResult:
    flags: RecoveryFlags
    discovered: int
    snapshot: str | None
    mode: str


def run_recovery_bootstrap(data_root: Path, logs_root: Path, config_root: Path) -> RecoveryBootstrapResult:
    flags_path = config_root / "recovery-flags.json"
    flags = load_recovery_flags(flags_path)
    if not flags.recovery_discovery:
        return RecoveryBootstrapResult(flags, 0, None, "disabled")
    history_root = logs_root / "renders"
    service = RecoveryService(history_root)
    candidates = service.discover()
    snapshot = data_root / "recovery-discovery.json"
    service.write_snapshot(snapshot)
    logging.getLogger(__name__).info(
        "Recovery discovery dry-run: %s job(s), snapshot=%s ring=%s",
        len(candidates), snapshot, flags.ring,
    )
    # The legacy Studio queue is intentionally not mutated here. Ring 3 is the
    # dry-run boundary; visible injection waits for launcher/UI acceptance.
    return RecoveryBootstrapResult(flags, len(candidates), str(snapshot), "dry-run")
