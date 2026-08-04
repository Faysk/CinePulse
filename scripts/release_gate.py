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
    bootstrap = json.loads((ROOT / "installer" / "bootstrap-manifest.json").read_text(encoding="utf-8-sig"))
    build_tools = json.loads((ROOT / "installer" / "build-tools.json").read_text(encoding="utf-8-sig"))
    require(channel.get("schema") == 1, "Canal de atualização incompatível", failures)
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
        "CinePulse.cmd", "Install-CinePulse.cmd", "LICENSE", "README.md", "SECURITY.md", "THIRD_PARTY_NOTICES.md",
        "requirements.lock", "installer/Start-CinePulse.ps1", "installer/wix/Product.wxs",
        "scripts/Build-Msi.ps1", "docs/VALIDATION.md",
    )
    for relative in required:
        require((ROOT / relative).is_file(), f"Arquivo obrigatório ausente: {relative}", failures)

    if failures:
        print("CINEPULSE_RELEASE_GATE_FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"CINEPULSE_RELEASE_GATE_OK version={package_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
