from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .paths import PATHS


MANIFEST_NAME = "cinepulse-files.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(root: Path = PATHS.root) -> dict:
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"available": False, "ok": None, "checked": 0, "missing": [], "changed": []}
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if payload.get("schema") != 1 or not isinstance(payload.get("files"), dict):
        raise ValueError("Manifesto de integridade incompatível.")
    missing: list[str] = []
    changed: list[str] = []
    for relative, expected in payload["files"].items():
        candidate = (root / relative).resolve()
        resolved_root = root.resolve()
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise ValueError(f"Caminho inseguro no manifesto: {relative}")
        if not candidate.is_file():
            missing.append(relative)
        elif sha256(candidate).lower() != str(expected).lower():
            changed.append(relative)
    return {
        "available": True,
        "ok": not missing and not changed,
        "checked": len(payload["files"]),
        "missing": missing,
        "changed": changed,
    }
