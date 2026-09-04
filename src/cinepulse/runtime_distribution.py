from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .job_lease import process_start_token
from .safe_output import process_alive


@dataclass(frozen=True)
class PowerShellChoice:
    executable: str
    modern: bool


def find_powershell() -> PowerShellChoice:
    """Use one resolver everywhere: PowerShell 7 first, Windows PowerShell only as fallback."""
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        preferred = Path(program_files) / "PowerShell" / "7" / "pwsh.exe"
        if preferred.is_file():
            return PowerShellChoice(str(preferred), True)
    discovered = shutil.which("pwsh.exe") or shutil.which("pwsh")
    if discovered:
        return PowerShellChoice(str(discovered), True)
    discovered = shutil.which("powershell.exe") or shutil.which("powershell")
    if discovered:
        return PowerShellChoice(str(discovered), False)
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        legacy = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if legacy.is_file():
            return PowerShellChoice(str(legacy), False)
    raise FileNotFoundError("PowerShell não encontrado. Instale PowerShell 7 ou habilite Windows PowerShell.")


def is_portable(root: Path) -> bool:
    return os.environ.get("CINEPULSE_PORTABLE") == "1" or (root / ".cinepulse-portable").is_file()


def installation_mode(root: Path) -> str:
    return "portable" if is_portable(root) else "installed"


def instance_mutex_name() -> str:
    identity = f"{Path.home().resolve()}|{os.environ.get('USERNAME') or os.environ.get('USER') or ''}"
    digest = hashlib.sha256(identity.encode("utf-8", "replace")).hexdigest()[:20]
    return f"Local\\CinePulse-{digest}"


def _windows_mutex_api():
    """Return Win32 mutex functions with pointer-sized signatures."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.ReleaseMutex.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


class InstanceGuard:
    """Single-instance guard with explicit ownership on every platform."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self._handle: int | None = None
        self._owns_file = False
        self._file_nonce: str | None = None

    def acquire(self) -> bool:
        if os.name == "nt":
            import ctypes

            kernel32 = _windows_mutex_api()
            ctypes.set_last_error(0)
            handle = kernel32.CreateMutexW(None, True, instance_mutex_name())
            if not handle:
                code = ctypes.get_last_error()
                raise OSError(code, "Não foi possível criar o mutex de instância do CinePulse.")
            already_exists = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
            if already_exists:
                kernel32.CloseHandle(handle)
                return False
            self._handle = int(handle)
            return True
        return self._acquire_file_lock()

    @staticmethod
    def _record_is_live(record: dict) -> bool:
        try:
            pid = int(record.get("pid") or 0)
        except (TypeError, ValueError):
            return False
        if not process_alive(pid):
            return False
        recorded_token = record.get("process_start")
        if recorded_token:
            current_token = process_start_token(pid)
            if current_token is not None and current_token != recorded_token:
                return False
        # Legacy schema-1 records do not have a start token. Keep them
        # conservative while that PID is alive; all newly written locks carry
        # a token and therefore recover correctly from PID reuse.
        return True

    def _acquire_file_lock(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        nonce = uuid.uuid4().hex
        payload = {
            "schema": 2,
            "pid": os.getpid(),
            "process_start": process_start_token(os.getpid()),
            "nonce": nonce,
            "started_at": time.time(),
        }
        for _ in range(3):
            try:
                descriptor = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    current = json.loads(self.lock_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    current = {}
                if self._record_is_live(current):
                    return False
                evidence = self.lock_path.with_name(f"{self.lock_path.name}.stale-{time.time_ns()}")
                try:
                    os.replace(self.lock_path, evidence)
                except FileNotFoundError:
                    pass
                continue
            else:
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                        json.dump(payload, stream, sort_keys=True)
                        stream.write("\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                except BaseException:
                    self.lock_path.unlink(missing_ok=True)
                    raise
                self._owns_file = True
                self._file_nonce = nonce
                return True
        return False

    def release(self) -> None:
        if os.name == "nt" and self._handle is not None:
            from ctypes import wintypes

            kernel32 = _windows_mutex_api()
            handle = wintypes.HANDLE(self._handle)
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
            self._handle = None
        if self._owns_file:
            try:
                current = json.loads(self.lock_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                current = {}
            if current.get("nonce") == self._file_nonce:
                self.lock_path.unlink(missing_ok=True)
            self._owns_file = False
            self._file_nonce = None

    def __enter__(self) -> "InstanceGuard":
        if not self.acquire():
            raise RuntimeError("Outra instância do CinePulse já está aberta.")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
