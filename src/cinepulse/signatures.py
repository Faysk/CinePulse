from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .paths import PATHS


def find_minisign() -> str | None:
    override = os.environ.get("CINEPULSE_MINISIGN", "").strip()
    candidates = [
        override or None,
        str(PATHS.root / "installer" / "tools" / "minisign.exe"),
        shutil.which("minisign.exe"),
        shutil.which("minisign"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() or shutil.which(candidate):
            return str(candidate)
    return None


def verify_file(message: Path, signature: Path, public_key: str, *, executable: str | None = None) -> None:
    key = str(public_key).strip()
    if not key:
        raise ValueError("Chave pública Minisign ausente.")
    verifier = executable or find_minisign()
    if not verifier:
        raise RuntimeError("Canal assinado configurado, mas o verificador Minisign não está disponível.")
    result = subprocess.run(
        [verifier, "-Vm", str(message), "-x", str(signature), "-P", key, "-q"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stdout or "").strip()
        raise RuntimeError(f"Assinatura Minisign inválida. {detail}".strip())


def verify_bytes(message: bytes, signature: bytes, public_key: str, *, executable: str | None = None) -> None:
    with tempfile.TemporaryDirectory(prefix="cinepulse-signature-") as directory:
        root = Path(directory)
        message_path = root / "manifest.json"
        signature_path = root / "manifest.minisig"
        message_path.write_bytes(message)
        signature_path.write_bytes(signature)
        verify_file(message_path, signature_path, public_key, executable=executable)
