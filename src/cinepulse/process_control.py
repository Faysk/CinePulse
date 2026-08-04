from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Callable


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def terminate_process_tree(process: subprocess.Popen | None, log: Callable[[str], None] | None = None) -> None:
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
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError) as exc:
        logger(f"Encerramento em árvore falhou; usando término direto: {exc}")
        try:
            process.terminate()
        except OSError:
            pass


def popen_group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}

