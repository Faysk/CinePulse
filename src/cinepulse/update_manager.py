from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .paths import PATHS


CHANNEL_FILE = PATHS.root / "installer" / "update-channel.json"


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    sha256: str
    notes_url: str | None = None


def _version_key(value: str) -> tuple[tuple[int, ...], int, int]:
    clean = value.strip().lower().lstrip("v")
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:(?:-|\.)?(alpha|a|beta|b|rc)(?:\.?)(\d+)?)?", clean)
    if not match:
        raise ValueError(f"Versão inválida no canal de atualização: {value}")
    numbers = tuple(int(part) for part in match.group(1).split("."))
    stage = match.group(2)
    rank = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2, None: 3}[stage]
    return numbers, rank, int(match.group(3) or 0)


def is_newer(candidate: str, current: str) -> bool:
    candidate_key = _version_key(candidate)
    current_key = _version_key(current)
    width = max(len(candidate_key[0]), len(current_key[0]))
    candidate_numbers = candidate_key[0] + (0,) * (width - len(candidate_key[0]))
    current_numbers = current_key[0] + (0,) * (width - len(current_key[0]))
    return (candidate_numbers, candidate_key[1], candidate_key[2]) > (
        current_numbers, current_key[1], current_key[2]
    )


def configured_feed() -> str | None:
    override = os.environ.get("CINEPULSE_UPDATE_MANIFEST", "").strip()
    if override:
        return override
    try:
        payload = json.loads(CHANNEL_FILE.read_text(encoding="utf-8-sig"))
        return str(payload.get("manifest_url") or "").strip() or None
    except (OSError, ValueError):
        return None


def _require_https(url: str) -> None:
    if urlparse(url).scheme.lower() != "https":
        raise ValueError("O canal de atualização precisa usar HTTPS.")


def check(feed_url: str, current_version: str, timeout: int = 15) -> UpdateInfo | None:
    _require_https(feed_url)
    request = urllib.request.Request(feed_url, headers={"User-Agent": f"CinePulse/{current_version}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read(1024 * 1024).decode("utf-8-sig"))
    if payload.get("schema") != 1:
        raise ValueError("Canal de atualização incompatível.")
    info = UpdateInfo(
        version=str(payload["version"]),
        download_url=str(payload["download_url"]),
        sha256=str(payload["sha256"]).lower(),
        notes_url=str(payload["notes_url"]) if payload.get("notes_url") else None,
    )
    _require_https(info.download_url)
    if not re.fullmatch(r"[0-9a-f]{64}", info.sha256):
        raise ValueError("O canal não contém um SHA-256 válido.")
    return info if is_newer(info.version, current_version) else None


def _safe_extract(archive: Path, destination: Path) -> Path:
    resolved = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            target = (destination / item.filename).resolve()
            if target != resolved and resolved not in target.parents:
                raise ValueError(f"Caminho inseguro no pacote: {item.filename}")
        bundle.extractall(destination)
    roots = [item for item in destination.iterdir() if item.is_dir()]
    package = roots[0] if len(roots) == 1 else destination
    if not (package / "CinePulse.cmd").is_file() or not (package / "pyproject.toml").is_file():
        raise ValueError("O pacote baixado não possui a estrutura do CinePulse.")
    return package


def stage(info: UpdateInfo) -> Path:
    if os.environ.get("CINEPULSE_PORTABLE") != "1" and not (PATHS.root / ".cinepulse-portable").exists():
        raise RuntimeError("A atualização automática está disponível no modo portátil.")
    runtime = PATHS.root / ".runtime"
    updates = runtime / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    staging = updates / info.version
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    archive = staging / "cinepulse.zip.part"
    request = urllib.request.Request(info.download_url, headers={"User-Agent": "CinePulse-Updater/1"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
            digest.update(block)
    if digest.hexdigest().lower() != info.sha256:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError("A atualização não passou na verificação SHA-256.")
    extracted = staging / "extracted"
    extracted.mkdir()
    package = _safe_extract(archive, extracted)
    archive.unlink()
    pending = runtime / "pending-update.json"
    descriptor, temporary_name = tempfile.mkstemp(prefix="pending-update-", suffix=".json", dir=runtime)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(
            json.dumps({"schema": 1, "version": info.version, "source": str(package.resolve())}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, pending)
    finally:
        temporary.unlink(missing_ok=True)
    return pending
