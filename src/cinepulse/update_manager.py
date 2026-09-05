from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

from .paths import PATHS
from .signatures import verify_bytes


CHANNEL_FILE = PATHS.root / "installer" / "update-channel.json"
DEFAULT_RELEASE_API = "https://api.github.com/repos/Faysk/CinePulse/releases/latest"
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
MAX_RELEASE_METADATA_BYTES = 2 * 1024 * 1024
MAX_CHECKSUM_BYTES = 256 * 1024
MAX_SIGNATURE_BYTES = 256 * 1024
MAX_UPDATE_ARCHIVE_BYTES = 2 * 1024**3
MAX_UPDATE_ENTRIES = 50_000
MAX_UPDATE_EXTRACTED_BYTES = 8 * 1024**3
_DOWNLOAD_BLOCK_BYTES = 1024 * 1024
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    sha256: str
    notes_url: str | None = None
    package_kind: str = "portable"
    asset_name: str | None = None
    source: str = "manifest"


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
    if info.package_kind not in {"portable", "msi"}:
        raise ValueError(f"Tipo de pacote de atualização inválido: {info.package_kind}")
    return version, digest


def check(feed_url: str, current_version: str, timeout: int = 15) -> UpdateInfo | None:
    """Check the optional manifest channel kept for controlled/private deployments."""
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
        package_kind=str(payload.get("package_kind") or "portable"),
        asset_name=str(payload["asset_name"]) if payload.get("asset_name") else None,
        source="manifest",
    )
    _validated_update_info(info)
    return info if is_newer(info.version, current_version) else None


def _release_api_url() -> str:
    override = os.environ.get("CINEPULSE_RELEASE_API", "").strip()
    return override or DEFAULT_RELEASE_API


def _github_request(url: str, current_version: str) -> urllib.request.Request:
    _require_https(url)
    return urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"CinePulse/{current_version}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )


def _asset_digest(asset: dict) -> str | None:
    value = str(asset.get("digest") or "").strip().lower()
    match = re.fullmatch(r"sha256:([0-9a-f]{64})", value)
    return match.group(1) if match else None


def _checksum_from_release_asset(
    assets: list[dict],
    asset_name: str,
    *,
    current_version: str,
    timeout: int,
) -> str:
    checksum_asset = next((item for item in assets if item.get("name") == "SHA256SUMS.txt"), None)
    if not checksum_asset:
        raise ValueError("Release não contém SHA256SUMS.txt nem digest SHA-256 do pacote.")
    url = str(checksum_asset.get("browser_download_url") or "")
    request = _github_request(url, current_version)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = _read_limited(response, MAX_CHECKSUM_BYTES, "SHA256SUMS.txt")
    wanted = asset_name.casefold()
    for line in raw.decode("utf-8-sig", errors="strict").splitlines():
        match = re.fullmatch(r"\s*([0-9A-Fa-f]{64})\s+\*?(.+?)\s*", line)
        if match and match.group(2).casefold() == wanted:
            return match.group(1).lower()
    raise ValueError(f"SHA256SUMS.txt não contém {asset_name}.")


def _validate_release_asset_url(url: str, version: str, asset_name: str) -> None:
    _require_https(url)
    parsed = urlparse(url)
    if parsed.hostname is None or parsed.hostname.casefold() != "github.com":
        raise ValueError("O pacote da release não aponta para github.com.")
    expected = f"/Faysk/CinePulse/releases/download/v{version}/{asset_name}"
    if unquote(parsed.path) != expected:
        raise ValueError("A URL do pacote não corresponde à release e ao arquivo esperados.")


def check_github_release(
    current_version: str,
    *,
    installation: str = "portable",
    timeout: int = 5,
) -> UpdateInfo | None:
    """Discover the latest verified Stable release with one lightweight API request.

    GitHub's release asset ``digest`` is preferred because it lets startup
    discovery finish without downloading a second metadata file. Older release
    metadata can still fall back to the published SHA256SUMS.txt asset.
    """
    api_url = _release_api_url()
    request = _github_request(api_url, current_version)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = _read_limited(response, MAX_RELEASE_METADATA_BYTES, "Metadados da release")
    payload = json.loads(raw.decode("utf-8-sig"))
    if payload.get("draft") or payload.get("prerelease"):
        return None
    tag = str(payload.get("tag_name") or "").strip()
    if not tag.startswith("v"):
        raise ValueError("A release Stable não possui tag vX.Y.Z válida.")
    version = tag[1:]
    _version_key(version)
    if not is_newer(version, current_version):
        return None

    package_kind = "msi" if installation == "installed" else "portable"
    asset_name = (
        f"CinePulse-{version}-Setup.msi"
        if package_kind == "msi"
        else f"CinePulse-{version}-windows-portable.zip"
    )
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError("A release não contém uma lista de assets válida.")
    asset = next(
        (
            item for item in assets
            if isinstance(item, dict)
            and item.get("name") == asset_name
            and str(item.get("state") or "uploaded") == "uploaded"
        ),
        None,
    )
    if asset is None:
        raise ValueError(f"A release {version} não contém o pacote esperado: {asset_name}.")
    download_url = str(asset.get("browser_download_url") or "")
    _validate_release_asset_url(download_url, version, asset_name)
    digest = _asset_digest(asset)
    if digest is None:
        digest = _checksum_from_release_asset(
            [item for item in assets if isinstance(item, dict)],
            asset_name,
            current_version=current_version,
            timeout=timeout,
        )
    notes_url = str(payload.get("html_url") or "").strip() or None
    info = UpdateInfo(
        version=version,
        download_url=download_url,
        sha256=digest,
        notes_url=notes_url,
        package_kind=package_kind,
        asset_name=asset_name,
        source="github-release",
    )
    _validated_update_info(info)
    return info


def check_available(
    current_version: str,
    *,
    installation: str = "portable",
    timeout: int = 5,
) -> UpdateInfo | None:
    """Resolve the user's update source without requiring a manually configured feed."""
    channel = configured_channel()
    if channel is not None and installation != "installed":
        return check(channel.manifest_url, current_version, timeout=timeout)
    return check_github_release(current_version, installation=installation, timeout=timeout)


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


def _stage_portable(info: UpdateInfo, version: str, expected_sha256: str) -> Path:
    if os.environ.get("CINEPULSE_PORTABLE") != "1" and not (PATHS.root / ".cinepulse-portable").exists():
        raise RuntimeError("A atualização portátil exige uma instalação CinePulse portátil.")
    runtime = PATHS.root / ".runtime"
    updates = runtime / "updates"
    updates.mkdir(parents=True, exist_ok=True)
    staging = updates / version
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    archive = staging / "cinepulse.zip.part"
    request = urllib.request.Request(info.download_url, headers={"User-Agent": "CinePulse-Updater/2"})
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


def _installed_update_root() -> Path:
    base = os.environ.get("LOCALAPPDATA", "").strip()
    root = Path(base) if base else Path(tempfile.gettempdir())
    return root / "CinePulseUpdater" / "updates"


def _stage_msi(info: UpdateInfo, version: str, expected_sha256: str) -> Path:
    asset_name = info.asset_name or Path(urlparse(info.download_url).path).name
    if not re.fullmatch(rf"CinePulse-{re.escape(version)}-Setup\.msi", asset_name):
        raise ValueError("O pacote MSI não corresponde à versão esperada.")
    staging = _installed_update_root() / version
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    partial = staging / f".{asset_name}.part"
    final = staging / asset_name
    request = urllib.request.Request(info.download_url, headers={"User-Agent": "CinePulse-Updater/2"})
    try:
        actual_sha256 = _download_limited(request, partial, MAX_UPDATE_ARCHIVE_BYTES)
        if actual_sha256 != expected_sha256:
            raise RuntimeError("A atualização MSI não passou na verificação SHA-256.")
        os.replace(partial, final)
        return final
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def stage(info: UpdateInfo) -> Path:
    version, expected_sha256 = _validated_update_info(info)
    if info.package_kind == "msi":
        return _stage_msi(info, version, expected_sha256)
    return _stage_portable(info, version, expected_sha256)


def _ps_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _powershell_executable() -> str:
    if os.name != "nt":
        raise RuntimeError("A aplicação automática da atualização é suportada no Windows.")
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    builtin = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if builtin.is_file():
        return str(builtin)
    candidate = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")
    if not candidate:
        raise RuntimeError("PowerShell não foi encontrado para concluir a atualização.")
    return candidate


def _handoff_script(info: UpdateInfo, staged: Path, app_root: Path, current_pid: int) -> str:
    root = app_root.expanduser().resolve()
    wait = max(1, int(current_pid))
    common = [
        "$ErrorActionPreference = 'Stop'",
        f"$PidToWait = {wait}",
        f"$AppRoot = {_ps_literal(root)}",
        "try { Wait-Process -Id $PidToWait -Timeout 120 -ErrorAction SilentlyContinue } catch { }",
        "if (Get-Process -Id $PidToWait -ErrorAction SilentlyContinue) { exit 21 }",
    ]
    if info.package_kind == "msi":
        launcher = root / "CinePulse-Installed.cmd"
        log_root = _installed_update_root().parent
        log_path = log_root / f"update-{info.version}.log"
        common += [
            f"$Msi = {_ps_literal(staged.resolve())}",
            f"$Launcher = {_ps_literal(launcher)}",
            f"$Log = {_ps_literal(log_path)}",
            "$Msiexec = Join-Path $env:SystemRoot 'System32\\msiexec.exe'",
            "& $Msiexec /i $Msi /passive /norestart CINEPULSE_SKIP_BOOTSTRAP=1 /L*v $Log",
            "$Code = $LASTEXITCODE",
            "if ($Code -notin @(0, 3010)) {",
            "  if (Test-Path -LiteralPath $Launcher) { Start-Process -FilePath $Launcher -WorkingDirectory $AppRoot }",
            "  exit $Code",
            "}",
            "Remove-Item -LiteralPath $Msi -Force -ErrorAction SilentlyContinue",
            "if (Test-Path -LiteralPath $Launcher) { Start-Process -FilePath $Launcher -WorkingDirectory $AppRoot }",
        ]
    else:
        launcher = root / "CinePulse.cmd"
        common += [
            f"$Pending = {_ps_literal(staged.resolve())}",
            f"$Launcher = {_ps_literal(launcher)}",
            "if (-not (Test-Path -LiteralPath $Pending)) { exit 22 }",
            "if (-not (Test-Path -LiteralPath $Launcher)) { exit 23 }",
            "Start-Process -FilePath $Launcher -WorkingDirectory $AppRoot",
        ]
    common += ["Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue"]
    return "\n".join(common) + "\n"


def launch_staged(info: UpdateInfo, staged: Path, app_root: Path, current_pid: int) -> Path:
    """Hand the verified package to a helper that waits for this process to exit.

    The helper lives outside the install tree so MSI MajorUpgrade can replace the
    application atomically after CinePulse closes. Portable updates simply
    relaunch CinePulse.cmd, whose existing pending-update transaction performs
    backup/rollback before the new application starts.
    """
    _validated_update_info(info)
    staged = Path(staged).expanduser().resolve()
    if not staged.exists():
        raise FileNotFoundError(f"Pacote de atualização preparado não encontrado: {staged}")
    if info.package_kind == "msi" and staged.suffix.lower() != ".msi":
        raise ValueError("A atualização instalada exige um pacote .msi preparado.")
    if info.package_kind == "portable" and staged.name != "pending-update.json":
        raise ValueError("A atualização portátil exige o descritor pending-update.json.")

    helper_root = Path(tempfile.gettempdir()) / "CinePulseUpdater" / "handoff"
    helper_root.mkdir(parents=True, exist_ok=True)
    helper = helper_root / f"apply-{info.version}-{os.getpid()}.ps1"
    helper.write_text(_handoff_script(info, staged, Path(app_root), current_pid), encoding="utf-8-sig")
    shell = _powershell_executable()
    subprocess.Popen(
        [shell, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(helper)],
        cwd=str(Path(app_root).resolve()),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )
    return helper
