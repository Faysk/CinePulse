from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Iterable

from .paths import PATHS


MANIFEST = PATHS.root / "installer" / "experimental-components.json"


def _catalog() -> dict:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    if payload.get("schema") != 1:
        raise RuntimeError("Manifesto experimental incompatível.")
    return payload["components"]


def metadata(key: str) -> dict:
    return _catalog().get(key, {})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _marker_matches(marker: Path, expected_hash: str) -> bool:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema") == 1
        and str(payload.get("sha256") or "").strip().lower() == expected_hash.strip().lower()
    )


def _download(url: str, destination: Path, expected_hash: str, log: Callable[[str], None]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and _sha256(destination).lower() == expected_hash.lower():
        log(f"Já verificado: {destination.name}")
        return
    partial = destination.with_name(destination.name + ".part")
    existing = partial.stat().st_size if partial.is_file() else 0
    headers = {"User-Agent": "CinePulse-Experimental/1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    log(f"{'Retomando' if existing else 'Baixando'} {destination.name}…")
    with urllib.request.urlopen(request, timeout=120) as response:
        resumed = existing > 0 and getattr(response, "status", 200) == 206
        if not resumed:
            existing = 0
        response_size = int(response.headers.get("Content-Length") or 0)
        total = existing + response_size if response_size else 0
        received = existing
        next_report = min(100, (int(received * 100 / total) // 10 + 1) * 10) if total else 10
        with partial.open("ab" if resumed else "wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                output.write(block)
                received += len(block)
                if total:
                    percent = int(received * 100 / total)
                    if percent >= next_report:
                        log(f"{destination.name}: {percent}%")
                        next_report = min(100, percent + 10)
    if _sha256(partial).lower() != expected_hash.lower():
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 inválido para {destination.name}; nada foi instalado.")
    os.replace(partial, destination)


def _install_archive(entry: dict, log: Callable[[str], None]) -> None:
    destination = PATHS.components / "ai" / entry["destination"]
    marker = destination / ".cinepulse-experimental.json"
    if _marker_matches(marker, entry["sha256"]):
        return
    staging = PATHS.components / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="experimental-", dir=staging) as temp_value:
        temp = Path(temp_value)
        archive = temp / "source.zip"
        _download(entry["url"], archive, entry["sha256"], log)
        unpacked = temp / "unpacked"
        with zipfile.ZipFile(archive) as bundle:
            root = unpacked.resolve()
            for member in bundle.infolist():
                target = (unpacked / member.filename).resolve()
                if target != root and root not in target.parents:
                    raise RuntimeError("O pacote experimental contém um caminho inseguro.")
            bundle.extractall(unpacked)
        roots = [item for item in unpacked.iterdir() if item.is_dir()]
        if len(roots) != 1:
            raise RuntimeError("Estrutura inesperada no pacote experimental.")
        previous = destination.with_name(destination.name + ".previous")
        if previous.exists():
            shutil.rmtree(previous)
        if destination.exists():
            os.replace(destination, previous)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(roots[0], destination)
            _atomic_json(marker, {"schema": 1, "sha256": entry["sha256"]})
        except Exception:
            try:
                if destination.exists():
                    shutil.rmtree(destination)
                if previous.exists():
                    os.replace(previous, destination)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"Falha ao instalar componente experimental e restaurar a versão anterior: {rollback_error}"
                ) from rollback_error
            raise
        if previous.exists():
            shutil.rmtree(previous)


def install(keys: Iterable[str], log: Callable[[str], None]) -> None:
    catalog = _catalog()
    selected = list(keys)
    required_bytes = 0
    for key in selected:
        entry = catalog.get(key, {})
        for asset in entry.get("assets", []):
            if not (PATHS.components / "ai" / asset["path"]).is_file():
                required_bytes += int(asset.get("bytes") or 0)
        archive = entry.get("archive")
        if archive:
            archive_marker = PATHS.components / "ai" / archive["destination"] / ".cinepulse-experimental.json"
            if not _marker_matches(archive_marker, archive["sha256"]):
                required_bytes += int(archive.get("bytes") or 0)
    free = shutil.disk_usage(PATHS.components).free
    reserve = 5 * 1024**3
    if free < required_bytes + reserve:
        raise RuntimeError(
            f"Espaço insuficiente: são necessários aproximadamente {required_bytes / 1024**3:.1f} GB "
            f"mais 5 GB de reserva; disponíveis {free / 1024**3:.1f} GB."
        )
    for key in selected:
        if key not in catalog:
            raise RuntimeError(f"Componente experimental desconhecido: {key}")
        entry = catalog[key]
        log(f"Componente experimental: {key} • licença: {entry['license']}")
        for asset in entry.get("assets", []):
            _download(asset["url"], PATHS.components / "ai" / asset["path"], asset["sha256"], log)
        if entry.get("archive"):
            _install_archive(entry["archive"], log)
        log(f"Arquivos experimentais prontos: {key}")
