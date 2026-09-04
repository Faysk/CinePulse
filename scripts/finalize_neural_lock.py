from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "Start-CinePulse.ps1"
PORTABLE = ROOT / "scripts" / "Build-Portable.ps1"
LOCK = ROOT / "requirements-neural.lock"

OLD_INSTALL = '''        & $UvExe pip install --python $AiPython --index-url $BootstrapManifest.demucs.torch_index `
            "torch==$($BootstrapManifest.demucs.torch_version)" `
            "torchaudio==$($BootstrapManifest.demucs.torchaudio_version)"
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar a aceleração PyTorch do Demucs.' }
        & $UvExe pip install --python $AiPython --index-url 'https://pypi.org/simple' `
            "demucs==$($BootstrapManifest.demucs.version)" soundfile
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o Demucs.' }
'''

NEW_INSTALL = '''        $NeuralLock = Join-Path $ProjectRoot 'requirements-neural.lock'
        if (-not (Test-Path -LiteralPath $NeuralLock)) {
            throw 'Lock neural ausente; recusando instalar dependências não reproduzíveis.'
        }
        & $UvExe pip install --python $AiPython --require-hashes -r $NeuralLock
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o runtime neural hash-locked do Demucs.' }
'''

OLD_ROOT_FILES = "        'pyproject.toml', 'requirements.lock'"
NEW_ROOT_FILES = "        'pyproject.toml', 'requirements.lock', 'requirements-neural.in', 'requirements-neural.lock'"
OLD_PORTABLE_FILES = "    'pyproject.toml', 'requirements.lock'"
NEW_PORTABLE_FILES = "    'pyproject.toml', 'requirements.lock', 'requirements-neural.in', 'requirements-neural.lock'"


def validate_lock() -> None:
    if not LOCK.is_file():
        raise RuntimeError("requirements-neural.lock ausente")
    text = LOCK.read_text(encoding="utf-8")
    required = ("torch==2.11.0+cu126", "torchaudio==2.11.0+cu126", "demucs==4.1.0", "--hash=sha256:")
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError("lock neural incompleto: " + ", ".join(missing))


def replace_once(text: str, old: str, new: str, label: str) -> tuple[str, bool]:
    if new in text:
        return text, False
    if old not in text:
        raise RuntimeError(f"bloco esperado não encontrado: {label}")
    return text.replace(old, new, 1), True


def main() -> int:
    validate_lock()
    changed: list[str] = []

    installer = INSTALLER.read_text(encoding="utf-8-sig")
    installer, install_changed = replace_once(installer, OLD_INSTALL, NEW_INSTALL, "instalação Demucs")
    installer, update_changed = replace_once(installer, OLD_ROOT_FILES, NEW_ROOT_FILES, "arquivos do updater")
    if install_changed or update_changed:
        INSTALLER.write_text(installer, encoding="utf-8-sig", newline="\n")
        changed.append(str(INSTALLER.relative_to(ROOT)))

    portable = PORTABLE.read_text(encoding="utf-8-sig")
    portable, portable_changed = replace_once(portable, OLD_PORTABLE_FILES, NEW_PORTABLE_FILES, "arquivos do pacote portátil")
    if portable_changed:
        PORTABLE.write_text(portable, encoding="utf-8-sig", newline="\n")
        changed.append(str(PORTABLE.relative_to(ROOT)))

    if changed:
        print("CINEPULSE_NEURAL_PACKAGING_LOCKED " + " ".join(changed))
    else:
        print("CINEPULSE_NEURAL_PACKAGING_ALREADY_LOCKED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CINEPULSE_NEURAL_PACKAGING_FAILED: {exc}", file=sys.stderr)
        raise
