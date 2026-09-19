from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# Keep the POSIX branch testable on Windows runners. Windows' signal module
# does not expose SIGKILL, even though the mocked POSIX path still needs the
# canonical POSIX signal numbers for os.killpg calls.
SIGTERM = getattr(signal, "SIGTERM", 15)
SIGKILL = getattr(signal, "SIGKILL", 9)


def _wait_for_exit(process: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout))
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    return process.poll() is not None


def _windows_process_table() -> dict[int, int]:
    """Return PID -> parent PID using Win32_Process.

    This is used only during cancellation. Capturing the real tree avoids the
    classic Windows shim race where the launcher exits before its FFmpeg child,
    leaving the child alive with the output file still locked.
    """
    if os.name != "nt":
        return {}
    script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "Get-CimInstance Win32_Process | ForEach-Object { "
        "Write-Output ($_.ProcessId.ToString() + ',' + $_.ParentProcessId.ToString()) }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    table: dict[int, int] = {}
    for raw in result.stdout.splitlines():
        left, separator, right = raw.strip().partition(",")
        if not separator:
            continue
        try:
            table[int(left)] = int(right)
        except ValueError:
            continue
    return table


def _windows_descendants(table: dict[int, int], root_pid: int) -> set[int]:
    by_parent: dict[int, list[int]] = {}
    for pid, parent in table.items():
        by_parent.setdefault(parent, []).append(pid)
    descendants: set[int] = set()
    pending = list(by_parent.get(int(root_pid), ()))
    while pending:
        pid = pending.pop()
        if pid in descendants:
            continue
        descendants.add(pid)
        pending.extend(by_parent.get(pid, ()))
    return descendants


def _windows_taskkill(pid: int) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _terminate_windows_tree(
    process: subprocess.Popen,
    logger: Callable[[str], None],
    grace_seconds: float,
) -> None:
    root_pid = int(process.pid)
    before = _windows_process_table()
    tracked = {root_pid} | _windows_descendants(before, root_pid)

    result = _windows_taskkill(root_pid)
    if result is not None and result.returncode not in (0, 128):
        logger(f"taskkill retornou {result.returncode}: {(result.stderr or result.stdout).strip()}")

    # taskkill /T is normally sufficient, but launcher/shim processes can exit
    # while a descendant is still alive. Re-scan the Win32 process table and
    # explicitly reap any captured or still-parented descendants before
    # returning to AtomicOutput cleanup.
    deadline = time.monotonic() + max(0.25, float(grace_seconds))
    remaining: set[int] = set()
    while time.monotonic() < deadline:
        table = _windows_process_table()
        if table:
            remaining = ({pid for pid in tracked if pid in table} | _windows_descendants(table, root_pid))
            remaining.discard(os.getpid())
        else:
            # CIM may be unavailable on stripped-down Windows images. Fall back
            # to the direct Popen state while preserving the existing behavior.
            remaining = {root_pid} if process.poll() is None else set()
        if not remaining:
            break
        for pid in sorted(remaining, reverse=True):
            if pid == root_pid and process.poll() is not None:
                continue
            _windows_taskkill(pid)
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        time.sleep(0.10)

    if process.poll() is None:
        logger(f"Processo {root_pid} não confirmou encerramento após taskkill; usando TerminateProcess.")
        try:
            process.kill()
            process.wait(timeout=2.0)
        except (OSError, subprocess.TimeoutExpired):
            logger(f"Processo {root_pid} não confirmou encerramento após TerminateProcess.")

    final_table = _windows_process_table()
    if final_table:
        survivors = ({pid for pid in tracked if pid in final_table} | _windows_descendants(final_table, root_pid))
        survivors.discard(os.getpid())
        if survivors:
            logger(
                "Descendentes Windows ainda visíveis após cancelamento: "
                + ", ".join(str(pid) for pid in sorted(survivors))
            )


def terminate_process_tree(
    process: subprocess.Popen | None,
    log: Callable[[str], None] | None = None,
    *,
    grace_seconds: float = 5.0,
) -> None:
    if process is None:
        return
    logger = log or (lambda _message: None)
    pid = process.pid
    try:
        if os.name == "nt":
            # Do not return merely because the launcher already exited: a
            # Chocolatey/WinGet shim may have left the real FFmpeg descendant
            # alive and holding the output file open.
            _terminate_windows_tree(process, logger, grace_seconds)
            return
        if process.poll() is not None:
            return
        else:
            pgid = os.getpgid(pid)
            os.killpg(pgid, SIGTERM)
            if not _wait_for_exit(process, grace_seconds):
                logger(f"Processo {pid} ignorou SIGTERM; escalando para SIGKILL.")
                try:
                    os.killpg(pgid, SIGKILL)
                except ProcessLookupError:
                    return
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    logger(f"Processo {pid} não confirmou encerramento após SIGKILL.")
    except (OSError, subprocess.SubprocessError) as exc:
        logger(f"Encerramento em árvore falhou; usando término direto: {exc}")
        try:
            process.terminate()
            if not _wait_for_exit(process, min(2.0, max(0.1, grace_seconds))):
                process.kill()
        except OSError:
            pass


def popen_group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
