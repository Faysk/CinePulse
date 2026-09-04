from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _wait_for_exit(process: subprocess.Popen, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.0, float(timeout))
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.05)
    return process.poll() is not None


def terminate_process_tree(
    process: subprocess.Popen | None,
    log: Callable[[str], None] | None = None,
    *,
    grace_seconds: float = 5.0,
) -> None:
    if process is None or process.poll() is not None:
        return
    logger = log or (lambda _message: None)
    pid = process.pid
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
                timeout=10,
            )
            if result.returncode not in (0, 128):
                logger(f"taskkill retornou {result.returncode}: {(result.stderr or result.stdout).strip()}")
        else:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            if not _wait_for_exit(process, grace_seconds):
                logger(f"Processo {pid} ignorou SIGTERM; escalando para SIGKILL.")
                try:
                    os.killpg(pgid, signal.SIGKILL)
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
