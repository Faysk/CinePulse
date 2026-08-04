from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .paths import PATHS, ensure_runtime_directories


CATALOG = Path(__file__).with_name("resources") / "components.catalog.json"


@dataclass(frozen=True)
class Component:
    key: str
    name: str
    category: str
    license: str
    homepage: str
    relative_path: str
    download_url: str | None = None
    sha256: str | None = None
    archive: str = "zip"

    @property
    def destination(self) -> Path:
        return PATHS.components / self.relative_path

    @property
    def installed(self) -> bool:
        return self.destination.exists()


def load_catalog(path: Path = CATALOG) -> list[Component]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != 1:
        raise ValueError("Catálogo de componentes incompatível.")
    return [Component(**entry) for entry in payload.get("components", [])]


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if target != resolved_destination and resolved_destination not in target.parents:
                raise ValueError(f"Arquivo inseguro no pacote: {member.filename}")
        bundle.extractall(destination)


def install(component: Component) -> Path:
    if not component.download_url or not component.sha256:
        raise RuntimeError(
            f"{component.name} requer instalação guiada; a origem e o hash ainda não foram fixados no catálogo."
        )
    ensure_runtime_directories()
    staging_root = PATHS.components / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{component.key}-", dir=staging_root) as temporary:
        temporary_path = Path(temporary)
        archive = temporary_path / "download.part"
        request = urllib.request.Request(component.download_url, headers={"User-Agent": "CinePulse/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        actual_hash = _hash(archive)
        if actual_hash.lower() != component.sha256.lower():
            raise RuntimeError(f"Hash inválido para {component.name}; a instalação foi cancelada.")
        unpacked = temporary_path / "unpacked"
        if component.archive != "zip":
            raise RuntimeError(f"Formato de pacote não suportado: {component.archive}")
        _safe_extract_zip(archive, unpacked)
        destination = component.destination
        backup = destination.with_name(destination.name + ".previous")
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            os.replace(destination, backup)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(unpacked, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        return destination


def inventory() -> list[dict]:
    return [
        {
            "key": item.key,
            "name": item.name,
            "category": item.category,
            "installed": item.installed,
            "license": item.license,
            "homepage": item.homepage,
            "managed_download": bool(item.download_url and item.sha256),
        }
        for item in load_catalog()
    ]

