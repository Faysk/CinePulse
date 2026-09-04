from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .storage_resilience import StorageGuard
from .volume_identity import resolve_volume_identity


class StagingError(RuntimeError):
    pass


@dataclass(frozen=True)
class CopyState:
    source: str
    source_size: int
    source_mtime_ns: int
    source_volume: str
    destination: str
    destination_volume: str
    copied_bytes: int
    total_bytes: int
    updated_at: float
    completed: bool
    checksum: str | None
    schema: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256_file(path: Path, *, chunk_size: int = 8 * 1024**2) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class ResumableStager:
    def __init__(self, *, guard: StorageGuard | None = None, chunk_size: int = 8 * 1024**2) -> None:
        self.guard = guard or StorageGuard()
        self.chunk_size = int(chunk_size)

    def _paths(self, destination: Path) -> tuple[Path, Path]:
        partial = destination.with_name(f".{destination.name}.staging.partial")
        state = destination.with_name(f".{destination.name}.staging.json")
        return partial, state

    def _identity(self, source: Path) -> tuple[int, int, str]:
        stat = source.stat()
        return stat.st_size, stat.st_mtime_ns, resolve_volume_identity(source).id

    def _load_state(self, path: Path) -> CopyState | None:
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StagingError(f"estado de staging inválido: {exc}") from exc
        if not isinstance(payload, dict) or int(payload.get("schema") or 0) != 1:
            raise StagingError("schema de staging inválido")
        return CopyState(**payload)

    @staticmethod
    def _state_matches_contract(
        state: CopyState,
        *,
        source: Path,
        source_size: int,
        source_mtime_ns: int,
        source_volume: str,
        destination: Path,
        destination_volume: str,
    ) -> bool:
        return (
            state.source == str(source)
            and state.source_size == source_size
            and state.source_mtime_ns == source_mtime_ns
            and state.source_volume == source_volume
            and state.destination == str(destination)
            and state.destination_volume == destination_volume
            and state.total_bytes == source_size
        )

    @staticmethod
    def _completed_state(
        *,
        source: Path,
        source_size: int,
        source_mtime_ns: int,
        source_volume: str,
        destination: Path,
        destination_volume: str,
        checksum: str | None,
    ) -> CopyState:
        return CopyState(
            source=str(source),
            source_size=source_size,
            source_mtime_ns=source_mtime_ns,
            source_volume=source_volume,
            destination=str(destination),
            destination_volume=destination_volume,
            copied_bytes=source_size,
            total_bytes=source_size,
            updated_at=time.time(),
            completed=True,
            checksum=checksum,
        )

    def _validate_promoted_destination(
        self,
        source: Path,
        destination: Path,
        state: CopyState,
        *,
        verify_checksum: bool,
        validator: Callable[[Path], None] | None,
        require_content_match: bool,
    ) -> str | None:
        if not destination.is_file():
            raise StagingError("checkpoint indica promoção concluída, mas o destino não existe")
        if destination.stat().st_size != state.source_size:
            raise StagingError("destino promovido possui tamanho divergente; recusando sobrescrever")

        checksum = state.checksum
        if require_content_match:
            # This path is only used to reconcile the narrow crash window after
            # atomic promotion and before completed=true is persisted. Hashing is
            # intentionally mandatory here so an unrelated/corrupted destination
            # is never accepted merely because its size matches.
            expected = checksum or sha256_file(source)
            actual = sha256_file(destination)
            if actual != expected:
                raise StagingError("destino promovido diverge da origem; recusando sobrescrever")
            checksum = actual
        elif checksum is not None or verify_checksum:
            expected = checksum or sha256_file(source)
            actual = sha256_file(destination)
            if actual != expected:
                raise StagingError("checksum do destino concluído diverge do contrato")
            checksum = actual

        if validator is not None:
            validator(destination)
        return checksum

    def copy(
        self,
        source: Path,
        destination: Path,
        *,
        verify_checksum: bool = False,
        validator: Callable[[Path], None] | None = None,
        progress: Callable[[int, int], None] | None = None,
        fault_after_bytes: int | None = None,
        fault_after_promote: bool = False,
    ) -> Path:
        requested_destination = Path(destination)
        source = source.resolve()
        destination = requested_destination.resolve(strict=False)
        if not source.is_file():
            raise FileNotFoundError(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_size, source_mtime, source_volume = self._identity(source)
        destination_volume = resolve_volume_identity(destination.parent).id
        partial, state_path = self._paths(destination)
        existing_state = self._load_state(state_path)
        resume_at = partial.stat().st_size if partial.is_file() else 0

        if existing_state is not None:
            if not self._state_matches_contract(
                existing_state,
                source=source,
                source_size=source_size,
                source_mtime_ns=source_mtime,
                source_volume=source_volume,
                destination=destination,
                destination_volume=destination_volume,
            ):
                raise StagingError("staging existente pertence a outra origem/contrato")

            if existing_state.completed:
                if partial.exists():
                    raise StagingError("checkpoint concluído ainda possui parcial; exige inspeção")
                checksum = self._validate_promoted_destination(
                    source,
                    destination,
                    existing_state,
                    verify_checksum=verify_checksum,
                    validator=validator,
                    require_content_match=False,
                )
                if checksum != existing_state.checksum:
                    _atomic_json(
                        state_path,
                        self._completed_state(
                            source=source,
                            source_size=source_size,
                            source_mtime_ns=source_mtime,
                            source_volume=source_volume,
                            destination=destination,
                            destination_volume=destination_volume,
                            checksum=checksum,
                        ).to_dict(),
                    )
                return requested_destination

            # Crash-safe reconciliation for the exact window between os.replace
            # and persisting completed=true. At that point the checkpoint records
            # all bytes copied, the partial no longer exists and the destination
            # already contains the promoted file.
            if (
                existing_state.copied_bytes == source_size
                and not partial.exists()
                and destination.is_file()
            ):
                checksum = self._validate_promoted_destination(
                    source,
                    destination,
                    existing_state,
                    verify_checksum=True,
                    validator=validator,
                    require_content_match=True,
                )
                _atomic_json(
                    state_path,
                    self._completed_state(
                        source=source,
                        source_size=source_size,
                        source_mtime_ns=source_mtime,
                        source_volume=source_volume,
                        destination=destination,
                        destination_volume=destination_volume,
                        checksum=checksum,
                    ).to_dict(),
                )
                return requested_destination

            if resume_at != existing_state.copied_bytes:
                raise StagingError(
                    f"parcial diverge do checkpoint: file={resume_at} state={existing_state.copied_bytes}"
                )
        elif resume_at:
            raise StagingError("parcial de staging órfão exige inspeção; recusando sobrescrever")
        if resume_at > source_size:
            raise StagingError("parcial é maior que a origem")

        self.guard.require(destination.parent, source_size - resume_at)
        _atomic_json(
            state_path,
            CopyState(
                source=str(source),
                source_size=source_size,
                source_mtime_ns=source_mtime,
                source_volume=source_volume,
                destination=str(destination),
                destination_volume=destination_volume,
                copied_bytes=resume_at,
                total_bytes=source_size,
                updated_at=time.time(),
                completed=False,
                checksum=None,
            ).to_dict(),
        )

        mode = "r+b" if partial.exists() else "wb"
        copied = resume_at
        with source.open("rb") as src, partial.open(mode) as dst:
            src.seek(resume_at)
            dst.seek(resume_at)
            while copied < source_size:
                self.guard.monitor(destination.parent)
                block = src.read(min(self.chunk_size, source_size - copied))
                if not block:
                    raise StagingError("origem terminou antes do tamanho registrado")
                dst.write(block)
                dst.flush()
                os.fsync(dst.fileno())
                copied += len(block)
                _atomic_json(
                    state_path,
                    CopyState(
                        source=str(source), source_size=source_size, source_mtime_ns=source_mtime,
                        source_volume=source_volume, destination=str(destination),
                        destination_volume=destination_volume, copied_bytes=copied,
                        total_bytes=source_size, updated_at=time.time(), completed=False, checksum=None,
                    ).to_dict(),
                )
                if progress:
                    progress(copied, source_size)
                if fault_after_bytes is not None and copied >= fault_after_bytes:
                    raise StagingError("fault injection after copied bytes")

        if partial.stat().st_size != source_size:
            raise StagingError("cópia completa possui tamanho divergente")
        checksum = None
        if verify_checksum:
            source_hash = sha256_file(source)
            staged_hash = sha256_file(partial)
            if source_hash != staged_hash:
                raise StagingError("checksum do staging diverge da origem")
            checksum = staged_hash
        if validator is not None:
            validator(partial)

        # Persist any checksum discovered before promotion. If the process dies
        # after os.replace, reconciliation can validate the already-promoted file
        # against this value without trusting size alone.
        _atomic_json(
            state_path,
            CopyState(
                source=str(source), source_size=source_size, source_mtime_ns=source_mtime,
                source_volume=source_volume, destination=str(destination),
                destination_volume=destination_volume, copied_bytes=source_size,
                total_bytes=source_size, updated_at=time.time(), completed=False, checksum=checksum,
            ).to_dict(),
        )
        os.replace(partial, destination)
        if fault_after_promote:
            raise StagingError("fault injection after staged promotion")
        _atomic_json(
            state_path,
            self._completed_state(
                source=source,
                source_size=source_size,
                source_mtime_ns=source_mtime,
                source_volume=source_volume,
                destination=destination,
                destination_volume=destination_volume,
                checksum=checksum,
            ).to_dict(),
        )
        # The state file keeps a canonical resolved path for restart matching,
        # while callers receive the same path representation they supplied.
        # On Windows this avoids changing an 8.3 path into its long-name alias.
        return requested_destination
