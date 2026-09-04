from pathlib import Path
import re

path = Path('installer/Start-CinePulse.ps1')
text = path.read_text(encoding='utf-8-sig')
pattern = re.compile(r"function Apply-PendingUpdate \{.*?\n\}\n\nif \(-not \$NonPortable\) \{", re.S)
replacement = r'''function Apply-PendingUpdate {
    $Applier = Join-Path $PSScriptRoot 'Apply-CinePulseUpdate.ps1'
    if (-not (Test-Path -LiteralPath $Applier)) { throw 'Aplicador transacional de atualização não encontrado.' }
    & $Applier -ProjectRoot $ProjectRoot -RuntimeRoot $RuntimeRoot
    if ($LASTEXITCODE -ne 0) { throw "Aplicador transacional de atualização falhou com código $LASTEXITCODE." }
}

if (-not $NonPortable) {'''
new, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f'expected one Apply-PendingUpdate function, got {count}')
path.write_text(new, encoding='utf-8-sig')
print('CINEPULSE_AUDIT_UPDATER_PATCH_OK')
