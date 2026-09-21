from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from .paths import PATHS


MANIFEST = PATHS.root / "installer" / "experimental-components.json"
MAX_ARCHIVE_ENTRIES = 50_000
MAX_ARCHIVE_EXTRACTED_BYTES = 2 * 1024**3


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


def _tree_fingerprint(root: Path) -> str:
    """Hash the installed archive tree, excluding CinePulse's own marker."""
    root = Path(root)
    if not root.is_dir():
        return ""
    digest = hashlib.sha256()
    try:
        entries = sorted(
            (path for path in root.rglob("*") if path.name != ".cinepulse-experimental.json"),
            key=lambda path: path.relative_to(root).as_posix().casefold(),
        )
        file_count = 0
        for path in entries:
            if path.is_symlink():
                return ""
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            stat_result = path.stat()
            digest.update(relative.encode("utf-8", "surrogatepass"))
            digest.update(b"\0")
            digest.update(str(stat_result.st_size).encode("ascii"))
            digest.update(b"\0")
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            digest.update(b"\0")
            file_count += 1
    except OSError:
        return ""
    if file_count <= 0:
        return ""
    return f"tree-v1:{file_count}:{digest.hexdigest()}"


def _marker_matches(marker: Path, expected_hash: str) -> bool:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != 2
        or str(payload.get("sha256") or "").strip().lower() != expected_hash.strip().lower()
    ):
        return False
    expected_tree = str(payload.get("tree_fingerprint") or "").strip()
    return bool(expected_tree and expected_tree == _tree_fingerprint(marker.parent))


def _download(
    url: str,
    destination: Path,
    expected_hash: str,
    log: Callable[[str], None],
    *,
    expected_bytes: int | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected_size = int(expected_bytes) if expected_bytes is not None else None
    if expected_size is not None and expected_size <= 0:
        raise RuntimeError(f"Tamanho esperado inválido para {destination.name}: {expected_size}.")

    if destination.is_file():
        actual_size = destination.stat().st_size
        size_ok = expected_size is None or actual_size == expected_size
        if size_ok and _sha256(destination).lower() == expected_hash.lower():
            log(f"Já verificado: {destination.name}")
            return
        # A destination that failed its pinned size/hash contract is not a
        # recoverable previous version. Removing it first prevents a corrupt
        # multi-gigabyte asset from doubling temporary disk pressure.
        destination.unlink()

    partial = destination.with_name(destination.name + ".part")
    existing = partial.stat().st_size if partial.is_file() else 0
    if expected_size is not None and existing > expected_size:
        partial.unlink(missing_ok=True)
        existing = 0

    if expected_size is not None:
        remaining = max(0, expected_size - existing)
        if shutil.disk_usage(destination.parent).free < remaining:
            raise RuntimeError(
                f"Espaço insuficiente para baixar {destination.name}: "
                f"faltam até {remaining} bytes do artefato verificado."
            )

    headers = {"User-Agent": "CinePulse-Experimental/1"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    log(f"{'Retomando' if existing else 'Baixando'} {destination.name}…")
    with urllib.request.urlopen(request, timeout=120) as response:
        resumed = existing > 0 and getattr(response, "status", 200) == 206
        if existing > 0 and not resumed:
            # The server ignored Range. Drop the stale partial before checking
            # headroom for a full restart; otherwise the old bytes consume disk
            # while our earlier estimate accounts only for the remainder.
            partial.unlink(missing_ok=True)
            existing = 0
            if expected_size is not None and shutil.disk_usage(destination.parent).free < expected_size:
                raise RuntimeError(
                    f"Espaço insuficiente para reiniciar o download completo de {destination.name}: "
                    f"são necessários {expected_size} bytes."
                )
        elif not resumed:
            existing = 0
        try:
            response_size = int(response.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            response_size = 0
        projected = existing + response_size if response_size else 0
        if expected_size is not None and projected > expected_size:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"Download de {destination.name} excede o tamanho fixado no manifesto "
                f"({projected} > {expected_size} bytes)."
            )
        total = projected or expected_size or 0
        received = existing
        next_report = min(100, (int(received * 100 / total) // 10 + 1) * 10) if total else 10
        with partial.open("ab" if resumed else "wb") as output:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                if expected_size is not None and received + len(block) > expected_size:
                    output.close()
                    partial.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"Download de {destination.name} excedeu o tamanho fixado "
                        f"de {expected_size} bytes."
                    )
                output.write(block)
                received += len(block)
                if total:
                    percent = int(received * 100 / total)
                    if percent >= next_report:
                        log(f"{destination.name}: {percent}%")
                        next_report = min(100, percent + 10)
            output.flush()
            os.fsync(output.fileno())

    if expected_size is not None and received != expected_size:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"Download incompleto para {destination.name}: "
            f"{received}/{expected_size} bytes recebidos."
        )
    if _sha256(partial).lower() != expected_hash.lower():
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 inválido para {destination.name}; nada foi instalado.")
    os.replace(partial, destination)
    _fsync_directory(destination.parent)


def _safe_extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    resolved = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise RuntimeError(
                f"O pacote experimental contém {len(infos)} entradas; limite é {MAX_ARCHIVE_ENTRIES}."
            )
        seen: set[str] = set()
        expanded = 0
        for member in infos:
            name = str(member.filename or "").replace("\\", "/")
            parts = PurePosixPath(name).parts
            unsafe = (
                not name
                or name.startswith("/")
                or ".." in parts
                or (parts and ":" in parts[0])
            )
            if unsafe:
                raise RuntimeError(f"O pacote experimental contém caminho inseguro: {member.filename}")
            canonical = "/".join(parts).casefold()
            if canonical in seen:
                raise RuntimeError(f"O pacote experimental contém entrada duplicada: {member.filename}")
            seen.add(canonical)
            mode = (member.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise RuntimeError(f"O pacote experimental contém link simbólico: {member.filename}")
            if member.flag_bits & 0x1:
                raise RuntimeError(f"O pacote experimental contém entrada criptografada: {member.filename}")
            expanded += max(0, int(member.file_size))
            if expanded > MAX_ARCHIVE_EXTRACTED_BYTES:
                raise RuntimeError(
                    f"O pacote experimental expandido excede {MAX_ARCHIVE_EXTRACTED_BYTES} bytes."
                )
            target = destination.joinpath(*parts).resolve()
            if target != resolved and resolved not in target.parents:
                raise RuntimeError(f"O pacote experimental contém caminho inseguro: {member.filename}")
        bundle.extractall(destination)


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
        _download(
            entry["url"],
            archive,
            entry["sha256"],
            log,
            expected_bytes=entry.get("bytes"),
        )
        unpacked = temp / "unpacked"
        _safe_extract_archive(archive, unpacked)
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
            tree_fingerprint = _tree_fingerprint(roots[0])
            if not tree_fingerprint:
                raise RuntimeError("O pacote experimental não contém uma árvore de arquivos válida.")
            os.replace(roots[0], destination)
            _atomic_json(
                marker,
                {
                    "schema": 2,
                    "sha256": entry["sha256"],
                    "tree_fingerprint": tree_fingerprint,
                },
            )
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
            asset_path = PATHS.components / "ai" / asset["path"]
            expected_size = int(asset.get("bytes") or 0)
            try:
                size_matches = asset_path.is_file() and asset_path.stat().st_size == expected_size
            except OSError:
                size_matches = False
            if not size_matches:
                required_bytes += expected_size
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
            _download(
                asset["url"],
                PATHS.components / "ai" / asset["path"],
                asset["sha256"],
                log,
                expected_bytes=asset.get("bytes"),
            )
        if entry.get("archive"):
            _install_archive(entry["archive"], log)
        log(f"Arquivos experimentais prontos: {key}")
