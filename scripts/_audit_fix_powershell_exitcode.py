from pathlib import Path

path = Path('installer/Start-CinePulse.ps1')
text = path.read_text(encoding='utf-8-sig')
old = '''    & $Applier -ProjectRoot $ProjectRoot -RuntimeRoot $RuntimeRoot
    if ($LASTEXITCODE -ne 0) { throw "Aplicador transacional de atualização falhou com código $LASTEXITCODE." }
'''
new = '''    try {
        & $Applier -ProjectRoot $ProjectRoot -RuntimeRoot $RuntimeRoot
    } catch {
        throw "Aplicador transacional de atualização falhou. $($_.Exception.Message)"
    }
'''
if old not in text:
    raise SystemExit('expected updater exit-code wrapper not found')
text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8-sig')
print('CINEPULSE_POWERSHELL_EXITCODE_FIX_OK')
