from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


PROTOCOL_SCHEMA = 1
COMMANDS = frozenset({"start", "pause", "resume", "cancel", "status", "shutdown"})


class WorkerProtocolError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkerCommand:
    request_id: str
    job_id: str
    command: str
    created_at: float
    payload: dict
    schema: int = PROTOCOL_SCHEMA

    @classmethod
    def create(cls, job_id: str, command: str, payload: dict | None = None) -> "WorkerCommand":
        if command not in COMMANDS:
            raise WorkerProtocolError(f"comando desconhecido: {command}")
        return cls(
            request_id=uuid.uuid4().hex,
            job_id=job_id,
            command=command,
            created_at=time.time(),
            payload=dict(payload or {}),
        )

    @classmethod
    def from_dict(cls, payload: dict) -> "WorkerCommand":
        if int(payload.get("schema") or 0) != PROTOCOL_SCHEMA:
            raise WorkerProtocolError("schema de comando inválido")
        command = str(payload.get("command") or "")
        if command not in COMMANDS:
            raise WorkerProtocolError(f"comando desconhecido: {command}")
        return cls(
            request_id=str(payload.get("request_id") or ""),
            job_id=str(payload.get("job_id") or ""),
            command=command,
            created_at=float(payload.get("created_at") or 0.0),
            payload=dict(payload.get("payload") or {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WorkerReply:
    request_id: str
    job_id: str
    ok: bool
    state: str
    message: str
    payload: dict
    created_at: float
    schema: int = PROTOCOL_SCHEMA

    def to_dict(self) -> dict:
        return asdict(self)


class WorkerCommandQueue:
    """Small local file protocol that survives UI disconnect/reconnect."""

    def __init__(self, root: Path, job_id: str) -> None:
        self.root = Path(root)
        self.job_id = job_id
        self.inbox = self.root / "commands" / "inbox"
        self.processing = self.root / "commands" / "processing"
        self.done = self.root / "commands" / "done"
        self.replies = self.root / "replies"
        for path in (self.inbox, self.processing, self.done, self.replies):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
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

    @classmethod
    def _atomic(cls, path: Path, payload: dict) -> None:
        temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            cls._fsync_directory(path.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def submit(self, command: WorkerCommand) -> Path:
        if command.job_id != self.job_id:
            raise WorkerProtocolError("command job_id diverge da fila")
        name = f"{time.time_ns():020d}-{command.request_id}.json"
        path = self.inbox / name
        self._atomic(path, command.to_dict())
        return path

    def recover_processing(self) -> dict[str, int]:
        """Reconcile commands claimed by a previous worker after lease takeover.

        The worker calls this only after acquiring the exclusive job lease. A
        command with an already-persisted reply was acknowledged before the old
        worker died and only needs its processing file finalized. Commands with
        no reply are returned to the inbox for idempotent reprocessing.
        """
        counts = {"requeued": 0, "finalized": 0, "invalid": 0}
        for claimed in sorted(self.processing.glob("*.json")):
            try:
                payload = json.loads(claimed.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise WorkerProtocolError("command file não contém objeto")
                command = WorkerCommand.from_dict(payload)
                if command.job_id != self.job_id or not command.request_id:
                    raise WorkerProtocolError("command recuperado não pertence à fila")
            except Exception:
                rejected = self.done / f"{claimed.stem}.invalid-{time.time_ns()}.json"
                os.replace(claimed, rejected)
                self._fsync_directory(self.processing)
                self._fsync_directory(self.done)
                counts["invalid"] += 1
                continue

            reply_path = self.replies / f"{command.request_id}.json"
            if reply_path.is_file():
                done_path = self.done / claimed.name
                if done_path.exists():
                    done_path = self.done / f"{claimed.stem}.recovered-{time.time_ns()}.json"
                os.replace(claimed, done_path)
                self._fsync_directory(self.processing)
                self._fsync_directory(self.done)
                counts["finalized"] += 1
                continue

            inbox_path = self.inbox / claimed.name
            if inbox_path.exists():
                try:
                    existing = json.loads(inbox_path.read_text(encoding="utf-8"))
                    existing_command = WorkerCommand.from_dict(existing)
                except Exception as exc:
                    raise WorkerProtocolError(
                        f"colisão de comando durante recovery: {claimed.name}"
                    ) from exc
                if existing_command.request_id != command.request_id:
                    raise WorkerProtocolError(f"colisão de comando durante recovery: {claimed.name}")
                # An equivalent inbox copy already guarantees retry. Preserve
                # only one executable command and archive the stale claim.
                done_path = self.done / f"{claimed.stem}.duplicate-{time.time_ns()}.json"
                os.replace(claimed, done_path)
                self._fsync_directory(self.processing)
                self._fsync_directory(self.done)
                counts["finalized"] += 1
                continue

            os.replace(claimed, inbox_path)
            self._fsync_directory(self.processing)
            self._fsync_directory(self.inbox)
            counts["requeued"] += 1
        return counts

    def next(self) -> tuple[WorkerCommand, Path] | None:
        for source in sorted(self.inbox.glob("*.json")):
            claimed = self.processing / source.name
            try:
                os.replace(source, claimed)
            except FileNotFoundError:
                continue
            try:
                payload = json.loads(claimed.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise WorkerProtocolError("command file não contém objeto")
                command = WorkerCommand.from_dict(payload)
                if command.job_id != self.job_id:
                    raise WorkerProtocolError("command job_id inválido")
                return command, claimed
            except Exception:
                rejected = self.done / (claimed.stem + ".invalid.json")
                os.replace(claimed, rejected)
                raise
        return None

    def acknowledge(self, command_path: Path, reply: WorkerReply) -> Path:
        reply_path = self.replies / f"{reply.request_id}.json"
        self._atomic(reply_path, reply.to_dict())
        done_path = self.done / command_path.name
        os.replace(command_path, done_path)
        return reply_path

    def read_reply(self, request_id: str) -> WorkerReply | None:
        path = self.replies / f"{request_id}.json"
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or int(payload.get("schema") or 0) != PROTOCOL_SCHEMA:
            raise WorkerProtocolError("reply inválido")
        return WorkerReply(
            request_id=str(payload.get("request_id") or ""),
            job_id=str(payload.get("job_id") or ""),
            ok=bool(payload.get("ok")),
            state=str(payload.get("state") or ""),
            message=str(payload.get("message") or ""),
            payload=dict(payload.get("payload") or {}),
            created_at=float(payload.get("created_at") or 0.0),
        )
