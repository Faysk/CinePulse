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


def _manifest_entries(payload: dict) -> list[tuple[str, str, int | None]]:
    """Normalize released Portable and MSI manifest shapes for verification."""
    if payload.get("schema") != 1:
        raise ValueError("Manifesto de integridade incompatível.")
    files = payload.get("files")
    entries: list[tuple[str, str, int | None]] = []
    if isinstance(files, dict):
        for relative, expected in files.items():
            entries.append((str(relative), str(expected), None))
        return entries
    if not isinstance(files, list):
        raise ValueError("Manifesto de integridade incompatível.")

    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Manifesto de integridade contém entrada inválida.")
        relative = str(item.get("path") or "").strip().replace("\\", "/").lstrip("/")
        expected = str(item.get("sha256") or "").strip().lower()
        size = item.get("size")
        if not relative or len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
            raise ValueError("Manifesto de integridade contém entrada inválida.")
        canonical = relative.casefold()
        if canonical in seen:
            raise ValueError(f"Manifesto de integridade contém caminho duplicado: {relative}")
        seen.add(canonical)
        try:
            expected_size = int(size) if size is not None else None
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Tamanho inválido no manifesto: {relative}") from exc
        if expected_size is not None and expected_size < 0:
            raise ValueError(f"Tamanho inválido no manifesto: {relative}")
        entries.append((relative, expected, expected_size))
    return entries


def verify(root: Path = PATHS.root) -> dict:
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"available": False, "ok": None, "checked": 0, "missing": [], "changed": []}
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Manifesto de integridade incompatível.")
    entries = _manifest_entries(payload)
    missing: list[str] = []
    changed: list[str] = []
    resolved_root = root.resolve()
    for relative, expected, expected_size in entries:
        candidate = (root / relative).resolve()
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise ValueError(f"Caminho inseguro no manifesto: {relative}")
        if not candidate.is_file():
            missing.append(relative)
            continue
        if expected_size is not None and candidate.stat().st_size != expected_size:
            changed.append(relative)
            continue
        if sha256(candidate).lower() != expected.lower():
            changed.append(relative)
    return {
        "available": True,
        "ok": not missing and not changed,
        "checked": len(entries),
        "missing": missing,
        "changed": changed,
    }
