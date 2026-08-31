from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .render_job import ManifestError, RenderJobManifest


class ManifestConflict(ManifestError):
    pass


class ManifestStoreError(ManifestError):
    pass


_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _thread_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve(strict=False)))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _json_bytes(manifest: RenderJobManifest) -> bytes:
    return (
        json.dumps(
            manifest.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class JobStore:
    """Durable compare-and-swap store for ``RenderJobManifest``.

    Phase 1 deliberately keeps worker ownership separate: this lock protects a
    manifest transaction inside the current process, while the Phase 2 job
    lease is responsible for cross-process execution ownership.  CAS/revision
    checks remain mandatory even when the lock is held so stale callers cannot
    silently overwrite newer state.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.backup_path = self.path.with_suffix(self.path.suffix + ".bak")
        self._lock = _thread_lock(self.path)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            yield

    def _parse(self, path: Path) -> RenderJobManifest:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestStoreError(f"não foi possível ler {path.name}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ManifestStoreError(f"{path.name} não contém um objeto JSON")
        return RenderJobManifest.from_dict(payload)

    def load(self, *, recover_backup: bool = True) -> RenderJobManifest:
        with self._lock:
            try:
                return self._parse(self.path)
            except ManifestError as primary_error:
                if not recover_backup or not self.backup_path.is_file():
                    raise
                try:
                    backup = self._parse(self.backup_path)
                except ManifestError as backup_error:
                    raise ManifestStoreError(
                        f"manifesto e backup inválidos: primary={primary_error}; backup={backup_error}"
                    ) from backup_error
                if self.path.exists():
                    evidence = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
                    try:
                        os.replace(self.path, evidence)
                    except OSError:
                        pass
                _atomic_bytes(self.path, _json_bytes(backup))
                return backup

    def create(self, manifest: RenderJobManifest) -> RenderJobManifest:
        with self._lock:
            if self.path.exists():
                raise ManifestConflict(f"manifesto já existe: {self.path}")
            _atomic_bytes(self.path, _json_bytes(manifest))
            stored = self._parse(self.path)
            if stored != manifest:
                raise ManifestStoreError("round-trip do manifesto alterou o conteúdo")
            return stored

    def save(self, manifest: RenderJobManifest, *, expected_revision: int) -> RenderJobManifest:
        with self._lock:
            current = self.load(recover_backup=True)
            if current.revision != expected_revision:
                raise ManifestConflict(
                    f"revision divergente: esperado {expected_revision}, atual {current.revision}"
                )
            if manifest.job_id != current.job_id:
                raise ManifestConflict("job_id não pode mudar durante save")
            if manifest.revision != current.revision + 1:
                raise ManifestConflict(
                    f"nova revision deve ser {current.revision + 1}, recebida {manifest.revision}"
                )
            if self.path.is_file():
                _atomic_bytes(self.backup_path, self.path.read_bytes())
            _atomic_bytes(self.path, _json_bytes(manifest))
            stored = self._parse(self.path)
            if stored.revision != manifest.revision or stored.job_id != manifest.job_id:
                raise ManifestStoreError("manifesto promovido não passou na revalidação")
            return stored

    def update(self, mutator: Callable[[RenderJobManifest], RenderJobManifest]) -> RenderJobManifest:
        with self._lock:
            current = self.load(recover_backup=True)
            updated = mutator(current)
            if not isinstance(updated, RenderJobManifest):
                raise TypeError("mutator deve retornar RenderJobManifest")
            return self.save(updated, expected_revision=current.revision)

    def transition(self, target: str, *, reason: str = "") -> RenderJobManifest:
        return self.update(lambda current: current.transition(target, reason=reason))

    def initialize(
        self,
        job_id: str,
        *,
        source: dict | None = None,
        begin_preflight: bool = True,
    ) -> RenderJobManifest:
        manifest = RenderJobManifest.new(job_id, source=source)
        self.create(manifest)
        if begin_preflight:
            return self.transition("preflight", reason="history_started")
        return manifest

    def remove_test_artifacts(self) -> None:
        """Test/helper cleanup; production cleanup remains an explicit later phase."""
        for path in (self.path, self.backup_path):
            path.unlink(missing_ok=True)
        for temporary in self.path.parent.glob(self.path.name + ".tmp-*"):
            temporary.unlink(missing_ok=True)
        for corrupt in self.path.parent.glob(self.path.name + ".corrupt-*"):
            corrupt.unlink(missing_ok=True)
