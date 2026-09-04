from __future__ import annotations

import ctypes
import json
import os
import socket
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable, Iterator


LEASE_SCHEMA = 1


class LeaseError(RuntimeError):
    pass


class LeaseBusy(LeaseError):
    pass


class LeaseOwnershipLost(LeaseError):
    pass


def _windows_process_api():
    """Return typed Win32 process functions.

    OpenProcess returns a pointer-sized HANDLE.  Leaving ctypes signatures
    implicit truncates handles on 64-bit Python, the same class of bug that the
    application instance mutex previously had.
    """
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _process_start_token_windows(pid: int) -> str | None:
    if os.name != "nt":
        return None
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = _windows_process_api()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return None
        value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        return f"win-filetime:{value}"
    finally:
        kernel32.CloseHandle(handle)


def _process_start_token_proc(pid: int) -> str | None:
    path = Path(f"/proc/{pid}/stat")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    # /proc/<pid>/stat field 22 is process starttime in clock ticks. The comm
    # field can contain spaces, so split only after the final ')'.
    try:
        tail = text[text.rindex(")") + 2 :].split()
        starttime = tail[19]
    except (ValueError, IndexError):
        return None
    return f"proc-start:{starttime}"


def process_start_token(pid: int) -> str | None:
    if pid <= 0:
        return None
    return _process_start_token_windows(pid) or _process_start_token_proc(pid)


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


@dataclass(frozen=True)
class LeaseRecord:
    job_id: str
    pid: int
    process_start: str | None
    nonce: str
    host_id: str
    acquired_at: float
    heartbeat_at: float
    progress_counter: int
    phase: str
    unit: str | None
    subprocesses: tuple[int, ...]
    schema: int = LEASE_SCHEMA

    @classmethod
    def from_dict(cls, payload: dict) -> "LeaseRecord":
        if int(payload.get("schema") or 0) != LEASE_SCHEMA:
            raise LeaseError("lease schema inválido")
        return cls(
            job_id=str(payload.get("job_id") or ""),
            pid=int(payload.get("pid") or 0),
            process_start=payload.get("process_start"),
            nonce=str(payload.get("nonce") or ""),
            host_id=str(payload.get("host_id") or ""),
            acquired_at=float(payload.get("acquired_at") or 0.0),
            heartbeat_at=float(payload.get("heartbeat_at") or 0.0),
            progress_counter=int(payload.get("progress_counter") or 0),
            phase=str(payload.get("phase") or ""),
            unit=str(payload.get("unit")) if payload.get("unit") is not None else None,
            subprocesses=tuple(int(item) for item in payload.get("subprocesses") or []),
        )

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["subprocesses"] = list(self.subprocesses)
        return payload


class JobLease:
    def __init__(
        self,
        path: Path,
        job_id: str,
        *,
        stale_after: float = 45.0,
        clock: Callable[[], float] = time.time,
        pid: int | None = None,
        process_token: Callable[[int], str | None] = process_start_token,
        alive: Callable[[int], bool] = process_alive,
        mutation_timeout: float = 5.0,
    ) -> None:
        self.path = Path(path)
        self.job_id = job_id
        self.stale_after = float(stale_after)
        self.clock = clock
        self.pid = int(os.getpid() if pid is None else pid)
        self._process_token = process_token
        self._alive = alive
        self.mutation_timeout = max(0.1, float(mutation_timeout))
        self.nonce: str | None = None

    @property
    def _guard_path(self) -> Path:
        return self.path.with_name(self.path.name + ".guard")

    def _guard_is_stale(self) -> bool:
        try:
            payload = json.loads(self._guard_path.read_text(encoding="utf-8"))
            pid = int(payload.get("pid") or 0)
            token = payload.get("process_start")
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            try:
                return time.time() - self._guard_path.stat().st_mtime > 30.0
            except OSError:
                return True
        if not self._alive(pid):
            return True
        current = self._process_token(pid)
        if token is not None and current is not None and current != token:
            return True
        return False

    @contextmanager
    def _mutation_guard(self) -> Iterator[None]:
        """Serialize lease compare-and-swap operations across processes.

        Without this fence, an old owner could read its nonce, a challenger
        could take over a stale lease, and the old owner could then os.replace
        the challenger's lease during heartbeat/release.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        guard = self._guard_path
        guard_nonce = uuid.uuid4().hex
        deadline = time.monotonic() + self.mutation_timeout
        while True:
            payload = {
                "schema": 1,
                "pid": self.pid,
                "process_start": self._process_token(self.pid),
                "nonce": guard_nonce,
                "created_at": time.time(),
            }
            try:
                descriptor = os.open(guard, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if self._guard_is_stale():
                    evidence = guard.with_name(f"{guard.name}.stale-{time.time_ns()}")
                    try:
                        os.replace(guard, evidence)
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise LeaseBusy(f"job {self.job_id} está com uma mutação de lease em andamento")
                time.sleep(0.01)
                continue
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                guard.unlink(missing_ok=True)
                raise
            break
        try:
            yield
        finally:
            try:
                current = json.loads(guard.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                current = {}
            if current.get("nonce") == guard_nonce:
                guard.unlink(missing_ok=True)

    def read(self) -> LeaseRecord | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise LeaseError(f"lease ilegível: {exc}") from exc
        if not isinstance(payload, dict):
            raise LeaseError("lease não contém objeto JSON")
        return LeaseRecord.from_dict(payload)

    def _same_process(self, record: LeaseRecord) -> bool:
        if record.host_id != socket.gethostname():
            return False
        if not self._alive(record.pid):
            return False
        current_start = self._process_token(record.pid)
        if record.process_start is None or current_start is None:
            return record.pid == self.pid and record.nonce == self.nonce
        return current_start == record.process_start

    def is_stale(self, record: LeaseRecord) -> bool:
        age = max(0.0, self.clock() - record.heartbeat_at)
        if age <= self.stale_after:
            return False
        if self._same_process(record):
            return False
        if any(self._alive(pid) for pid in record.subprocesses):
            return False
        return True

    def acquire(self, *, phase: str = "preflight", unit: str | None = None) -> LeaseRecord:
        with self._mutation_guard():
            existing = self.read()
            if existing is not None:
                if not self.is_stale(existing):
                    raise LeaseBusy(
                        f"job {self.job_id} já possui owner pid={existing.pid} nonce={existing.nonce[:8]}"
                    )
                evidence = self.path.with_name(f"{self.path.name}.stale-{int(self.clock())}-{existing.nonce[:8]}")
                try:
                    os.replace(self.path, evidence)
                except FileNotFoundError:
                    pass
            nonce = uuid.uuid4().hex
            now = self.clock()
            record = LeaseRecord(
                job_id=self.job_id,
                pid=self.pid,
                process_start=self._process_token(self.pid),
                nonce=nonce,
                host_id=socket.gethostname(),
                acquired_at=now,
                heartbeat_at=now,
                progress_counter=0,
                phase=phase,
                unit=unit,
                subprocesses=(),
            )
            payload = json.dumps(record.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise LeaseBusy(f"job {self.job_id} foi adquirido por outro worker") from exc
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                self.path.unlink(missing_ok=True)
                raise
            self.nonce = nonce
            return record

    def _owned(self) -> LeaseRecord:
        record = self.read()
        if record is None or self.nonce is None or record.nonce != self.nonce:
            raise LeaseOwnershipLost(f"lease do job {self.job_id} não pertence mais a este worker")
        return record

    def heartbeat(
        self,
        *,
        phase: str | None = None,
        unit: str | None = None,
        progress: bool = False,
        subprocesses: tuple[int, ...] | None = None,
    ) -> LeaseRecord:
        with self._mutation_guard():
            current = self._owned()
            updated = replace(
                current,
                heartbeat_at=self.clock(),
                progress_counter=current.progress_counter + (1 if progress else 0),
                phase=current.phase if phase is None else phase,
                unit=current.unit if unit is None else unit,
                subprocesses=current.subprocesses if subprocesses is None else tuple(subprocesses),
            )
            _atomic_json(self.path, updated.to_dict())
            return updated

    def release(self) -> None:
        with self._mutation_guard():
            current = self._owned()
            released = self.path.with_name(f"{self.path.name}.released-{int(self.clock())}-{current.nonce[:8]}")
            try:
                os.replace(self.path, released)
            except FileNotFoundError as exc:
                raise LeaseOwnershipLost("lease desapareceu antes do release") from exc
            self.nonce = None

    def __enter__(self) -> "JobLease":
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self.nonce is not None:
            self.release()
