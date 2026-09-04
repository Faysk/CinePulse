from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

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
    """Return Win32 mutex functions with pointer-sized signatures.

    ctypes assumes ``c_int`` for an undeclared function result.  A Windows
    HANDLE is pointer-sized, so leaving CreateMutexW untyped can truncate the
    handle in a 64-bit process and make ReleaseMutex/CloseHandle unreliable.
    """
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
    """Single-instance guard.

    Windows uses a per-user named mutex. Other platforms use an atomic PID lock,
    which also makes the behavior testable in CI without pretending to emulate Win32.
    """

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = Path(lock_path)
        self._handle: int | None = None
        self._owns_file = False

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

    def _acquire_file_lock(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": 1, "pid": os.getpid(), "started_at": time.time()}
        for _ in range(2):
            try:
                descriptor = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    current = json.loads(self.lock_path.read_text(encoding="utf-8"))
                    pid = int(current.get("pid") or 0)
                except (OSError, ValueError, TypeError):
                    pid = 0
                if process_alive(pid):
                    return False
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            else:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream)
                self._owns_file = True
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
                self.lock_path.unlink()
            except FileNotFoundError:
                pass
            self._owns_file = False

    def __enter__(self) -> "InstanceGuard":
        if not self.acquire():
            raise RuntimeError("Outra instância do CinePulse já está aberta.")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
