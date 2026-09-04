from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .job_lease import JobLease
from .job_store import JobStore
from .render_job import RenderJobManifest
from .worker_protocol import WorkerCommand, WorkerCommandQueue, WorkerReply


class WorkerPaused(RuntimeError):
    pass


class WorkerCancelled(RuntimeError):
    pass


class WorkerExecutor(Protocol):
    def __call__(self, context: "WorkerContext") -> None: ...


@dataclass
class WorkerContext:
    worker: "RenderWorker"
    pause_requested: bool = False
    cancel_requested: bool = False

    def _reply(self, command: WorkerCommand, command_path: Path, *, ok: bool, message: str) -> None:
        state = self.worker.store.load().state
        self.worker.commands.acknowledge(
            command_path,
            WorkerReply(
                request_id=command.request_id,
                job_id=command.job_id,
                ok=ok,
                state=state,
                message=message,
                payload={},
                created_at=time.time(),
            ),
        )

    def poll_commands(self) -> None:
        while True:
            item = self.worker.commands.next()
            if item is None:
                return
            command, command_path = item
            if command.command == "pause":
                if not self.pause_requested:
                    current = self.worker.store.load()
                    if current.state == "running":
                        self.worker.store.transition("pause_requested", reason="worker_pause_requested")
                    self.pause_requested = True
                self._reply(command, command_path, ok=True, message="pausa solicitada")
            elif command.command == "cancel":
                self.cancel_requested = True
                self._reply(command, command_path, ok=True, message="cancelamento solicitado")
            elif command.command == "status":
                self._reply(command, command_path, ok=True, message="status atualizado")
            elif command.command == "shutdown":
                self.pause_requested = True
                self._reply(command, command_path, ok=True, message="shutdown cooperativo solicitado")
            elif command.command in {"start", "resume"}:
                self._reply(command, command_path, ok=False, message="worker já possui esta execução")
            else:
                self._reply(command, command_path, ok=False, message="comando não suportado")

    def checkpoint(
        self,
        *,
        phase: str,
        unit: str | None = None,
        progress: bool = True,
        subprocesses: tuple[int, ...] = (),
    ) -> None:
        self.poll_commands()
        self.worker.lease.heartbeat(
            phase=phase,
            unit=unit,
            progress=progress,
            subprocesses=subprocesses,
        )
        if self.cancel_requested:
            raise WorkerCancelled("cancelamento solicitado")
        if self.pause_requested:
            raise WorkerPaused("pausa solicitada na fronteira segura")


class RenderWorker:
    """Tk-independent durable execution owner."""

    def __init__(
        self,
        job_dir: Path,
        job_id: str,
        *,
        stale_after: float = 45.0,
        lease_factory: Callable[..., JobLease] = JobLease,
    ) -> None:
        self.job_dir = Path(job_dir)
        self.job_id = job_id
        self.store = JobStore(self.job_dir / "manifest.json")
        self.commands = WorkerCommandQueue(self.job_dir, job_id)
        self.lease = lease_factory(self.job_dir / "lease.json", job_id, stale_after=stale_after)

    def _enter_running(self) -> RenderJobManifest:
        current = self.store.load()
        if current.state == "queued":
            current = self.store.transition("preflight", reason="worker_start")
        elif current.state == "paused":
            current = self.store.transition("recoverable", reason="worker_resume")
        if current.state == "recoverable":
            current = self.store.transition("preflight", reason="worker_resume_preflight")
        if current.state == "preflight":
            current = self.store.transition("running", reason="worker_acquired")
        if current.state != "running":
            raise RuntimeError(f"job não pode iniciar worker a partir de {current.state}")
        return current

    def _mark_cancelled(self) -> RenderJobManifest:
        """Persist cancellation through only valid manifest transitions."""
        current = self.store.load()
        if current.state == "cancelled":
            return current
        if current.state == "pause_requested":
            current = self.store.transition("paused", reason="worker_cancel_after_pause")
        if current.state in {"preflight", "running", "paused", "recoverable", "blocked"}:
            return self.store.transition("cancelled", reason="worker_cancelled")
        raise RuntimeError(f"cancelamento não pode ser persistido a partir de {current.state}")

    def run(self, executor: WorkerExecutor) -> RenderJobManifest:
        self.lease.acquire(phase="preflight")
        context = WorkerContext(self)
        try:
            self._enter_running()
            self.lease.heartbeat(phase="running", progress=True)
            executor(context)
            context.poll_commands()
            if context.cancel_requested:
                raise WorkerCancelled("cancelamento solicitado")
            if context.pause_requested:
                raise WorkerPaused("pausa solicitada")
            current = self.store.load()
            if current.state == "running":
                return self.store.transition("verifying", reason="worker_execution_finished")
            return current
        except WorkerPaused:
            current = self.store.load()
            if current.state == "running":
                current = self.store.transition("pause_requested", reason="worker_pause_boundary")
            if current.state == "pause_requested":
                current = self.store.transition("paused", reason="worker_paused")
            return current
        except WorkerCancelled:
            return self._mark_cancelled()
        except Exception as exc:
            self.store.update(
                lambda manifest: manifest.with_error(
                    code="WORKER-FAILED",
                    message=f"{type(exc).__name__}: {exc}",
                    retryable=True,
                )
            )
            current = self.store.load()
            if current.state in {"preflight", "running", "verifying"}:
                try:
                    current = self.store.transition("blocked", reason="worker_failed")
                except Exception:
                    pass
            raise
        finally:
            if self.lease.nonce is not None:
                self.lease.release()
