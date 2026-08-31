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
    def _atomic(path: Path, payload: dict) -> None:
        temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def submit(self, command: WorkerCommand) -> Path:
        if command.job_id != self.job_id:
            raise WorkerProtocolError("command job_id diverge da fila")
        name = f"{time.time_ns():020d}-{command.request_id}.json"
        path = self.inbox / name
        self._atomic(path, command.to_dict())
        return path

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
