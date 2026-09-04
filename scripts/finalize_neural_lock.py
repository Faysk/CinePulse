from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "Start-CinePulse.ps1"
LOCK = ROOT / "requirements-neural.lock"

OLD = '''        & $UvExe pip install --python $AiPython --index-url $BootstrapManifest.demucs.torch_index `
            "torch==$($BootstrapManifest.demucs.torch_version)" `
            "torchaudio==$($BootstrapManifest.demucs.torchaudio_version)"
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar a aceleração PyTorch do Demucs.' }
        & $UvExe pip install --python $AiPython --index-url 'https://pypi.org/simple' `
            "demucs==$($BootstrapManifest.demucs.version)" soundfile
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o Demucs.' }
'''

NEW = '''        $NeuralLock = Join-Path $ProjectRoot 'requirements-neural.lock'
        if (-not (Test-Path -LiteralPath $NeuralLock)) {
            throw 'Lock neural ausente; recusando instalar dependências não reproduzíveis.'
        }
        & $UvExe pip install --python $AiPython --require-hashes -r $NeuralLock
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o runtime neural hash-locked do Demucs.' }
'''


def validate_lock() -> None:
    if not LOCK.is_file():
        raise RuntimeError("requirements-neural.lock ausente")
    text = LOCK.read_text(encoding="utf-8")
    required = ("torch==2.11.0+cu126", "torchaudio==2.11.0+cu126", "demucs==4.1.0", "--hash=sha256:")
    missing = [item for item in required if item not in text]
    if missing:
        raise RuntimeError("lock neural incompleto: " + ", ".join(missing))


def main() -> int:
    validate_lock()
    text = INSTALLER.read_text(encoding="utf-8-sig")
    if NEW in text:
        print("CINEPULSE_NEURAL_INSTALLER_ALREADY_LOCKED")
        return 0
    if OLD not in text:
        raise RuntimeError("bloco esperado do instalador Demucs não foi encontrado")
    updated = text.replace(OLD, NEW, 1)
    INSTALLER.write_text(updated, encoding="utf-8-sig", newline="\n")
    print("CINEPULSE_NEURAL_INSTALLER_LOCKED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CINEPULSE_NEURAL_INSTALLER_FAILED: {exc}", file=sys.stderr)
        raise
