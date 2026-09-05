from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def canonical(value: str) -> str:
    return value.strip().lower().replace("-alpha.", "a").replace("-beta.", "b").replace("-rc.", "rc").replace("-rc", "rc")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = project["project"]["version"]
    init_text = (ROOT / "src" / "cinepulse" / "__init__.py").read_text(encoding="utf-8")
    init_match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    build_text = (ROOT / "scripts" / "Build-Portable.ps1").read_text(encoding="utf-8-sig")
    build_match = re.search(r"\[string\]\$Version\s*=\s*'([^']+)'", build_text)
    require(bool(init_match), "Versão ausente em __init__.py", failures)
    require(bool(build_match), "Versão padrão ausente no empacotador", failures)
    if init_match:
        require(canonical(init_match.group(1)) == canonical(package_version), "Versão do pacote e do aplicativo divergem", failures)
    if build_match:
        require(canonical(build_match.group(1)) == canonical(package_version), "Versão do pacote e do empacotador divergem", failures)

    channel = json.loads((ROOT / "installer" / "update-channel.json").read_text(encoding="utf-8-sig"))
    update_manager_text = (ROOT / "src" / "cinepulse" / "update_manager.py").read_text(encoding="utf-8")
    publisher_text = (ROOT / ".github" / "workflows" / "publish-release.yml").read_text(encoding="utf-8")
    bootstrap = json.loads((ROOT / "installer" / "bootstrap-manifest.json").read_text(encoding="utf-8-sig"))
    build_tools = json.loads((ROOT / "installer" / "build-tools.json").read_text(encoding="utf-8-sig"))
    require(channel.get("schema") in {1, 2}, "Canal de atualização incompatível", failures)
    manifest_url = str(channel.get("manifest_url") or "").strip()
    if manifest_url:
        require(manifest_url.startswith("https://"), "Manifesto de atualização precisa usar HTTPS", failures)
        require(bool(channel.get("require_signature")), "Canal remoto de produção precisa exigir assinatura", failures)
        require(bool(str(channel.get("public_key") or "").strip()), "Canal remoto assinado sem chave pública", failures)
        signature_url = str(channel.get("manifest_signature_url") or "").strip()
        require(signature_url.startswith("https://"), "Canal remoto assinado sem URL HTTPS da assinatura", failures)
    github_release_contract = all(
        token in update_manager_text
        for token in (
            'https://api.github.com/repos/Faysk/CinePulse/releases/latest',
            '_validate_release_asset_url',
            'SHA256SUMS.txt',
            'A release Stable precisa usar versão final x.y.z',
            '_sha256_file(staged)',
        )
    )
    publisher_contract = all(
        token in publisher_text
        for token in (
            'Stable publisher requires x.y.z SemVer',
            'dist/SHA256SUMS.txt',
            'gh release',
        )
    )
    require(github_release_contract, "Updater GitHub Stable sem contrato de origem/hash completo", failures)
    require(publisher_contract, "Publisher não garante assets/hash da release consumida pelo updater", failures)

    for name in ("uv", "ffmpeg", "real_esrgan", "rife"):
        item = bootstrap.get(name, {})
        require(str(item.get("url", "")).startswith("https://"), f"URL insegura para {name}", failures)
        require(bool(re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")).lower())), f"SHA-256 inválido para {name}", failures)
    demucs = bootstrap.get("demucs", {})
    require(bool(demucs.get("version")), "Versão do Demucs ausente", failures)
    require(bool(demucs.get("torch_version")), "Versão do PyTorch ausente", failures)
    for weight in demucs.get("weights", []):
        require(str(weight.get("url", "")).startswith("https://"), f"URL insegura para {weight.get('file', 'peso Demucs')}", failures)
        require(bool(re.fullmatch(r"[0-9a-f]{64}", str(weight.get("sha256", "")).lower())), f"SHA-256 inválido para {weight.get('file', 'peso Demucs')}", failures)
    require(len(demucs.get("weights", [])) == 4, "Conjunto htdemucs_ft incompleto", failures)
    sdk = build_tools.get("dotnet_sdk", {})
    require(str(sdk.get("url", "")).startswith("https://"), "URL insegura para SDK .NET", failures)
    require(bool(re.fullmatch(r"[0-9a-f]{128}", str(sdk.get("sha512", "")).lower())), "SHA-512 inválido para SDK .NET", failures)

    required = (
        "CinePulse.cmd", "Install-CinePulse.cmd", "CinePulse-Installed.cmd", "Install-CinePulse-Installed.cmd",
        "LICENSE", "README.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md", "requirements.lock",
        "requirements-neural.in", "requirements-neural.lock",
        "assets/cinepulse.ico", "installer/Start-CinePulse.ps1", "installer/wix/Product.wxs",
        "scripts/Build-Msi.ps1", "scripts/Test-MsiLifecycle.ps1", "scripts/generate_sbom.py", "scripts/ci_gate.py", "docs/VALIDATION.md",
        ".github/workflows/quality.yml", ".github/workflows/release-candidate.yml", ".github/workflows/gpu-acceptance.yml",
        "docs/CORE_INTEGRITY_PHASE9_CI_RELEASE_GATES.md", "docs/FINAL_AUDIT_RC_ACCEPTANCE.md",
        "docs/RC_ACCEPTANCE_CHECKLIST.md", "scripts/final_audit.py", "scripts/Invoke-RcAcceptance.ps1",
    )
    for relative in required:
        require((ROOT / relative).is_file(), f"Arquivo obrigatório ausente: {relative}", failures)

    requirements = (ROOT / "requirements.lock").read_text(encoding="utf-8")
    require("--hash=sha256:" in requirements, "Lock do runtime sem hash", failures)
    neural_lock_path = ROOT / "requirements-neural.lock"
    if neural_lock_path.is_file():
        neural_lock = neural_lock_path.read_text(encoding="utf-8")
        for package in (str(demucs.get("version") or ""), str(demucs.get("torch_version") or ""), str(demucs.get("torchaudio_version") or "")):
            if package:
                require(package in neural_lock, f"Lock neural não contém versão esperada: {package}", failures)
        require("--hash=sha256:" in neural_lock, "Lock neural sem hashes transitivos", failures)
    start_script = (ROOT / "installer" / "Start-CinePulse.ps1").read_text(encoding="utf-8-sig")
    require("--python-preference only-managed" in start_script, "Runtime gerenciado não é obrigatório", failures)
    require("Find-SystemPython" not in start_script, "Bootstrap ainda depende do Python do sistema", failures)
    require("requirements-neural.lock" in start_script, "Instalador neural ainda não consome o lock transitivo", failures)
    require("--require-hashes" in start_script, "Instalador neural não exige hashes", failures)
    wix = (ROOT / "installer" / "wix" / "Product.wxs").read_text(encoding="utf-8-sig")
    require("$(var.ProductVersion)" in wix, "Versão MSI continua fixa", failures)
    require("CinePulse-Installed.cmd" in wix, "MSI ainda usa launcher portátil", failures)
    require("CinePulseIcon" in wix, "Branding do MSI sem ícone", failures)

    if failures:
        print("CINEPULSE_RELEASE_GATE_FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    update_source = "signed-manifest+github-installed" if manifest_url else "github-release"
    print(f"CINEPULSE_RELEASE_GATE_OK version={package_version} update_source={update_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
