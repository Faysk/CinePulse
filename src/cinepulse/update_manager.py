from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .paths import PATHS
from .signatures import verify_bytes


CHANNEL_FILE = PATHS.root / "installer" / "update-channel.json"
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
MAX_SIGNATURE_BYTES = 256 * 1024
MAX_UPDATE_ARCHIVE_BYTES = 2 * 1024**3
MAX_UPDATE_ENTRIES = 50_000
MAX_UPDATE_EXTRACTED_BYTES = 8 * 1024**3
_DOWNLOAD_BLOCK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    sha256: str
    notes_url: str | None = None


@dataclass(frozen=True)
class UpdateChannel:
    manifest_url: str
    require_signature: bool = False
    public_key: str | None = None
    manifest_signature_url: str | None = None


def configured_channel() -> UpdateChannel | None:
    override = os.environ.get("CINEPULSE_UPDATE_MANIFEST", "").strip()
    if override:
        return UpdateChannel(
            override,
            os.environ.get("CINEPULSE_UPDATE_REQUIRE_SIGNATURE") == "1",
            os.environ.get("CINEPULSE_UPDATE_PUBLIC_KEY", "").strip() or None,
            os.environ.get("CINEPULSE_UPDATE_SIGNATURE", "").strip() or None,
        )
    try:
        payload = json.loads(CHANNEL_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    schema = int(payload.get("schema") or 0)
    if schema not in {1, 2}:
        raise ValueError("Configuração do canal de atualização incompatível.")
    manifest_url = str(payload.get("manifest_url") or "").strip()
    if not manifest_url:
        return None
    require_signature = bool(payload.get("require_signature", False))
    public_key = str(payload.get("public_key") or "").strip() or None
    signature_url = str(payload.get("manifest_signature_url") or "").strip() or None
    if require_signature and (not public_key or not signature_url):
        raise ValueError("Canal assinado incompleto: chave pública e URL da assinatura são obrigatórias.")
    return UpdateChannel(manifest_url, require_signature, public_key, signature_url)


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
    channel = configured_channel()
    return channel.manifest_url if channel else None


def _require_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise ValueError("O canal de atualização precisa usar HTTPS.")


def _read_limited(response, limit: int, label: str) -> bytes:
    data = response.read(max(0, int(limit)) + 1)
    if len(data) > limit:
        raise ValueError(f"{label} excede o limite de {limit} bytes.")
    return data


def _download_limited(request: urllib.request.Request, destination: Path, max_bytes: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
        headers = getattr(response, "headers", None)
        declared_value = headers.get("Content-Length") if headers is not None else None
        if declared_value:
            try:
                declared = int(declared_value)
            except (TypeError, ValueError):
                declared = 0
            if declared > max_bytes:
                raise ValueError(f"Pacote de atualização declara {declared} bytes; limite é {max_bytes}.")
        while True:
            block = response.read(_DOWNLOAD_BLOCK_BYTES)
            if not block:
                break
            total += len(block)
            if total > max_bytes:
                raise ValueError(f"Pacote de atualização excede o limite de {max_bytes} bytes.")
            output.write(block)
            digest.update(block)
        output.flush()
        os.fsync(output.fileno())
    return digest.hexdigest().lower()


def _validated_update_info(info: UpdateInfo) -> tuple[str, str]:
    """Validate the staging trust boundary even for internally constructed UpdateInfo."""
    version = info.version.strip()
    if not version:
        raise ValueError("A versão da atualização está vazia.")
    _version_key(version)
    _require_https(info.download_url)
    if info.notes_url:
        _require_https(info.notes_url)
    digest = info.sha256.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("A atualização não contém um SHA-256 válido.")
    return version, digest


def check(feed_url: str, current_version: str, timeout: int = 15) -> UpdateInfo | None:
    _require_https(feed_url)
    request = urllib.request.Request(feed_url, headers={"User-Agent": f"CinePulse/{current_version}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw_manifest = _read_limited(response, MAX_MANIFEST_BYTES, "Manifesto de atualização")
    channel = configured_channel()
    if channel and channel.manifest_url == feed_url and channel.require_signature:
        assert channel.public_key and channel.manifest_signature_url
        _require_https(channel.manifest_signature_url)
        signature_request = urllib.request.Request(channel.manifest_signature_url, headers={"User-Agent": f"CinePulse/{current_version}"})
        with urllib.request.urlopen(signature_request, timeout=timeout) as response:
            raw_signature = _read_limited(response, MAX_SIGNATURE_BYTES, "Assinatura do manifesto")
        verify_bytes(raw_manifest, raw_signature, channel.public_key)
    payload = json.loads(raw_manifest.decode("utf-8-sig"))
    if payload.get("schema") != 1:
        raise ValueError("Canal de atualização incompatível.")
    info = UpdateInfo(
        version=str(payload["version"]),
        download_url=str(payload["download_url"]),
        sha256=str(payload["sha256"]).lower(),
        notes_url=str(payload["notes_url"]) if payload.get("notes_url") else None,
    )
    _validated_update_info(info)
    return info if is_newer(info.version, current_version) else None


def _normalized_zip_parts(name: str) -> tuple[str, ...]:
    pure = PurePosixPath(str(name or "").replace("\\", "/"))
    parts = tuple(part for part in pure.parts if part not in ("", "."))
    if pure.is_absolute() or not parts or any(part == ".." for part in parts):
        raise ValueError(f"Caminho inseguro no pacote: {name}")
    if ":" in parts[0]:
        raise ValueError(f"Drive inválido no pacote: {name}")
    return parts


def _safe_extract(archive: Path, destination: Path) -> Path:
    resolved = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) > MAX_UPDATE_ENTRIES:
            raise ValueError(f"Pacote contém {len(infos)} entradas; limite é {MAX_UPDATE_ENTRIES}.")
        expanded = 0
        seen: set[str] = set()
        for item in infos:
            parts = _normalized_zip_parts(item.filename)
            canonical = "/".join(parts).casefold()
            if canonical in seen:
                raise ValueError(f"Entrada duplicada no pacote: {item.filename}")
            seen.add(canonical)
            mode = (item.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError(f"Link simbólico não suportado no pacote: {item.filename}")
            if item.flag_bits & 0x1:
                raise ValueError(f"Entrada criptografada não suportada no pacote: {item.filename}")
            expanded += max(0, int(item.file_size))
            if expanded > MAX_UPDATE_EXTRACTED_BYTES:
                raise ValueError(f"Pacote expandido excede o limite de {MAX_UPDATE_EXTRACTED_BYTES} bytes.")
            target = destination.joinpath(*parts).resolve()
            if target != resolved and resolved not in target.parents:
                raise ValueError(f"Caminho inseguro no pacote: {item.filename}")
        bundle.extractall(destination)
    roots = [item for item in destination.iterdir() if item.is_dir()]
    package = roots[0] if len(roots) == 1 else destination
    if not (package / "CinePulse.cmd").is_file() or not (package / "pyproject.toml").is_file():
        raise ValueError("O pacote baixado não possui a estrutura do CinePulse.")
    return package


def stage(info: UpdateInfo) -> Path:
    version, expected_sha256 = _validated_update_info(info)
    if os.environ.get("CINEPULSE_PORTABLE") != "1" and not (PATHS.root / ".cinepulse-portable").exists():
        raise RuntimeError("A atualização automática está disponível no modo portátil.")
    runtime = PATHS.root / ".runtime"
    updates = runtime / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    staging = updates / version
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    archive = staging / "cinepulse.zip.part"
    request = urllib.request.Request(info.download_url, headers={"User-Agent": "CinePulse-Updater/1"})
    try:
        actual_sha256 = _download_limited(request, archive, MAX_UPDATE_ARCHIVE_BYTES)
        if actual_sha256 != expected_sha256:
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
                json.dumps({"schema": 1, "version": version, "source": str(package.resolve())}, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, pending)
        finally:
            temporary.unlink(missing_ok=True)
        return pending
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
