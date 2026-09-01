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

    def copy(
        self,
        source: Path,
        destination: Path,
        *,
        verify_checksum: bool = False,
        validator: Callable[[Path], None] | None = None,
        progress: Callable[[int, int], None] | None = None,
        fault_after_bytes: int | None = None,
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
            matches = (
                existing_state.source == str(source)
                and existing_state.source_size == source_size
                and existing_state.source_mtime_ns == source_mtime
                and existing_state.source_volume == source_volume
                and existing_state.destination == str(destination)
            )
            if not matches:
                raise StagingError("staging existente pertence a outra origem/contrato")
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
        os.replace(partial, destination)
        _atomic_json(
            state_path,
            CopyState(
                source=str(source), source_size=source_size, source_mtime_ns=source_mtime,
                source_volume=source_volume, destination=str(destination),
                destination_volume=destination_volume, copied_bytes=source_size,
                total_bytes=source_size, updated_at=time.time(), completed=True, checksum=checksum,
            ).to_dict(),
        )
        # The state file keeps a canonical resolved path for restart matching,
        # while callers receive the same path representation they supplied.
        # On Windows this avoids changing an 8.3 path into its long-name alias.
        return requested_destination
