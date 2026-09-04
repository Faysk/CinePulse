from pathlib import Path

path = Path('installer/Start-CinePulse.ps1')
text = path.read_text(encoding='utf-8-sig')
old = """        & $UvExe pip install --python $AiPython --require-hashes -r $NeuralLock
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o runtime neural hash-locked do Demucs.' }
"""
new = """        $TorchIndex = [string]$BootstrapManifest.demucs.torch_index
        if (-not $TorchIndex.StartsWith('https://download.pytorch.org/whl/', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Índice oficial do PyTorch ausente ou inválido no manifesto de bootstrap.'
        }
        Write-Host \"Resolvendo PyTorch $($BootstrapManifest.demucs.torch_version) pelo índice oficial CUDA: $TorchIndex\"
        & $UvExe pip install --python $AiPython --require-hashes --index $TorchIndex -r $NeuralLock
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o runtime neural hash-locked do Demucs.' }
"""
if text.count(old) != 1:
    raise SystemExit(f'expected exactly one neural install block, found {text.count(old)}')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8-sig')
print('CINEPULSE_NEURAL_INDEX_PATCH_OK')
