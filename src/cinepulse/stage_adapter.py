from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .stage_checkpoint import StageCheckpointStore


class StageCommitError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    details: dict


Producer = Callable[[Path], None]
Validator = Callable[[Path], ValidationResult]
FaultHook = Callable[[str, str], None]


def _noop_fault(_point: str, _unit_id: str) -> None:
    return None


class AtomicStageAdapter:
    """Idempotent unit commit protocol shared by long-running stages."""

    def __init__(
        self,
        checkpoint: StageCheckpointStore,
        *,
        fault_hook: FaultHook = _noop_fault,
    ) -> None:
        self.checkpoint = checkpoint
        self.fault_hook = fault_hook

    @staticmethod
    def _partial_for(final: Path, unit_id: str) -> Path:
        return final.with_name(f".{final.name}.partial-{unit_id}-{uuid.uuid4().hex[:8]}")

    def _validate(self, path: Path, validator: Validator) -> ValidationResult:
        result = validator(path)
        if not isinstance(result, ValidationResult):
            raise TypeError("validator deve retornar ValidationResult")
        if not result.passed:
            raise StageCommitError(f"validação recusou {path.name}: {result.details}")
        return result

    def reconcile(
        self,
        *,
        unit_id: str,
        ordinal: int,
        final: Path,
        validator: Validator,
        contract: dict | None = None,
    ) -> bool:
        committed = self.checkpoint.committed(unit_id)
        if committed is not None:
            if not final.is_file():
                raise StageCommitError(f"checkpoint {unit_id} está committed mas artefato sumiu")
            self._validate(final, validator)
            return True
        if not final.is_file():
            return False
        result = self._validate(final, validator)
        self.checkpoint.record(
            unit_id=unit_id,
            ordinal=ordinal,
            state="committed",
            artifact=str(final),
            contract=contract,
            validation=result.details,
        )
        return True

    def execute_unit(
        self,
        *,
        unit_id: str,
        ordinal: int,
        final: Path,
        producer: Producer,
        validator: Validator,
        contract: dict | None = None,
        cleanup: Callable[[], None] | None = None,
    ) -> Path:
        final = Path(final)
        final.parent.mkdir(parents=True, exist_ok=True)
        if self.reconcile(
            unit_id=unit_id,
            ordinal=ordinal,
            final=final,
            validator=validator,
            contract=contract,
        ):
            return final

        partial = self._partial_for(final, unit_id)
        self.checkpoint.record(
            unit_id=unit_id,
            ordinal=ordinal,
            state="producing",
            artifact=str(partial),
            contract=contract,
        )
        self.fault_hook("before_produce", unit_id)
        try:
            producer(partial)
            self.fault_hook("after_produce", unit_id)
            if not partial.is_file() or partial.stat().st_size <= 0:
                raise StageCommitError(f"producer não materializou {partial.name}")
            self.checkpoint.record(
                unit_id=unit_id,
                ordinal=ordinal,
                state="validating",
                artifact=str(partial),
                contract=contract,
            )
            result = self._validate(partial, validator)
            self.fault_hook("after_validate", unit_id)
            os.replace(partial, final)
            self.fault_hook("after_promote", unit_id)
            self.checkpoint.record(
                unit_id=unit_id,
                ordinal=ordinal,
                state="committed",
                artifact=str(final),
                contract=contract,
                validation=result.details,
            )
            self.fault_hook("after_checkpoint", unit_id)
            if cleanup is not None:
                cleanup()
            self.fault_hook("after_cleanup", unit_id)
            return final
        except BaseException:
            # A promoted final is intentionally never deleted here. If failure
            # happened after os.replace but before the checkpoint, next resume
            # validates/reconciles it. An unpromoted partial remains evidence.
            if not final.exists():
                try:
                    current = self.checkpoint.load()["units"].get(unit_id)
                    state = current.get("state") if isinstance(current, dict) else None
                    if state in {"producing", "validating"}:
                        self.checkpoint.record(
                            unit_id=unit_id,
                            ordinal=ordinal,
                            state="interrupted",
                            artifact=str(partial),
                            contract=contract,
                        )
                except Exception:
                    pass
            raise


def file_validator(
    *,
    minimum_bytes: int = 1,
    expected_bytes: bytes | None = None,
) -> Validator:
    def validate(path: Path) -> ValidationResult:
        try:
            size = path.stat().st_size
        except OSError as exc:
            return ValidationResult(False, {"error": str(exc)})
        details = {"size": size, "validated_at": time.time()}
        if size < minimum_bytes:
            return ValidationResult(False, {**details, "error": "too_small"})
        if expected_bytes is not None and path.read_bytes() != expected_bytes:
            return ValidationResult(False, {**details, "error": "content_mismatch"})
        return ValidationResult(True, details)

    return validate
