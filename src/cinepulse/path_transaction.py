from __future__ import annotations

import ctypes
import hashlib
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Callable, Iterator, ParamSpec, TypeVar


_P = ParamSpec("_P")
_R = TypeVar("_R")
_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}
_THREAD_STATE = threading.local()


def _path_key(path: Path) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=False)))


def path_mutation_lock(path: Path) -> threading.RLock:
    """Return the in-process reentrant lock for one durable path."""
    key = _path_key(path)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _windows_mutex_name(key: str) -> str:
    token = hashlib.sha256(key.encode("utf-8", errors="surrogatepass")).hexdigest()
    return rf"Local\CinePulsePathMutation-{token}"


def _acquire_windows_mutex(key: str, timeout: float):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    kernel32.WaitForSingleObject.restype = ctypes.c_uint32
    handle = kernel32.CreateMutexW(None, False, _windows_mutex_name(key))
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    timeout_ms = max(0, min(0xFFFFFFFE, int(float(timeout) * 1000)))
    result = kernel32.WaitForSingleObject(handle, timeout_ms)
    if result in (0x00000000, 0x00000080):  # WAIT_OBJECT_0 / WAIT_ABANDONED
        return kernel32, handle
    kernel32.CloseHandle(handle)
    if result == 0x00000102:  # WAIT_TIMEOUT
        raise TimeoutError(f"timed out waiting for CinePulse path mutation lock: {key}")
    raise OSError(f"WaitForSingleObject failed for CinePulse path mutation lock: result={result}")


def _release_windows_mutex(resource) -> None:
    kernel32, handle = resource
    try:
        if not kernel32.ReleaseMutex(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)


def _acquire_posix_lock(key: str, timeout: float):
    import fcntl

    lock_root = Path(tempfile.gettempdir()) / "cinepulse-path-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    token = hashlib.sha256(key.encode("utf-8", errors="surrogatepass")).hexdigest()
    handle = (lock_root / f"{token}.lock").open("a+b")
    deadline = time.monotonic() + max(0.0, float(timeout))
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return handle
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for CinePulse path mutation lock: {key}")
                time.sleep(0.02)
    except BaseException:
        handle.close()
        raise


def _release_posix_lock(handle) -> None:
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def path_mutation_transaction(path: Path, *, timeout: float = 30.0) -> Iterator[None]:
    """Serialize a durable path mutation across threads *and* processes.

    Tuning/evidence CLIs can run beside the Studio and target the same JSON
    stores. Atomic replace prevents torn files but does not make
    read-modify-write atomic; this transaction closes that lost-update window.

    The OS lock is acquired only by the outermost call on a thread so nested
    store methods remain reentrant. Windows uses a named mutex (released by the
    kernel on process death); POSIX uses flock on a hashed file in the system
    temp directory.
    """
    target = Path(path)
    key = _path_key(target)
    lock = path_mutation_lock(target)
    with lock:
        depths = getattr(_THREAD_STATE, "depths", None)
        if depths is None:
            depths = {}
            _THREAD_STATE.depths = depths
        depth = int(depths.get(key, 0))
        if depth:
            depths[key] = depth + 1
            try:
                yield
            finally:
                remaining = int(depths.get(key, 1)) - 1
                if remaining:
                    depths[key] = remaining
                else:
                    depths.pop(key, None)
            return

        resource = _acquire_windows_mutex(key, timeout) if os.name == "nt" else _acquire_posix_lock(key, timeout)
        depths[key] = 1
        try:
            yield
        finally:
            depths.pop(key, None)
            if os.name == "nt":
                _release_windows_mutex(resource)
            else:
                _release_posix_lock(resource)


def serialized_path_mutation(method: Callable[_P, _R]) -> Callable[_P, _R]:
    """Serialize a store read-modify-write transaction across the machine."""
    @wraps(method)
    def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        if not args:
            return method(*args, **kwargs)
        owner = args[0]
        path = Path(getattr(owner, "path"))
        with path_mutation_transaction(path):
            return method(*args, **kwargs)
    return guarded
