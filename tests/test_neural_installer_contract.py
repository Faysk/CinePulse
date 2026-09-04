from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_neural_installer_uses_manifest_pytorch_index() -> None:
    manifest = json.loads((ROOT / "installer" / "bootstrap-manifest.json").read_text(encoding="utf-8"))
    torch_index = manifest["demucs"]["torch_index"]
    installer = (ROOT / "installer" / "Start-CinePulse.ps1").read_text(encoding="utf-8-sig")
    assert torch_index.startswith("https://download.pytorch.org/whl/")
    assert "$BootstrapManifest.demucs.torch_index" in installer
    assert "--index $TorchIndex" in installer


def test_neural_input_lock_and_manifest_are_aligned() -> None:
    manifest = json.loads((ROOT / "installer" / "bootstrap-manifest.json").read_text(encoding="utf-8"))
    neural_input = (ROOT / "requirements-neural.in").read_text(encoding="utf-8")
    neural_lock = (ROOT / "requirements-neural.lock").read_text(encoding="utf-8")
    demucs = manifest["demucs"]
    assert f"--extra-index-url {demucs['torch_index']}" in neural_input
    assert f"torch=={demucs['torch_version']}" in neural_input
    assert f"torchaudio=={demucs['torchaudio_version']}" in neural_input
    assert f"torch=={demucs['torch_version']}" in neural_lock
    assert f"torchaudio=={demucs['torchaudio_version']}" in neural_lock
