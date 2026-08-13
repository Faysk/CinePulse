[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.runtime\python\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    $PythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
    if (-not $PythonCommand) { $PythonCommand = Get-Command 'py' -ErrorAction SilentlyContinue }
    if (-not $PythonCommand) { throw 'Python não encontrado para executar o portão de release.' }
    $Python = $PythonCommand.Source
}

& (Join-Path $PSScriptRoot 'Check-Repository.ps1')
if (-not $?) { throw 'A higiene do repositório falhou.' }
$env:PYTHONPATH = Join-Path $ProjectRoot 'src'
& $Python (Join-Path $PSScriptRoot 'ci_gate.py') --profile source --output (Join-Path $ProjectRoot 'artifacts\ci\source-powershell.json')
if ($LASTEXITCODE -ne 0) { throw 'O portão source da Phase 9 falhou.' }

Get-ChildItem -LiteralPath $ProjectRoot -Recurse -File -Filter '*.ps1' |
    Where-Object { $_.FullName -notlike '*\.runtime\*' -and $_.FullName -notlike '*\components\*' } |
    ForEach-Object {
        $Tokens = $null
        $Errors = $null
        [void][Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$Tokens, [ref]$Errors)
        if ($Errors.Count) { throw "PowerShell inválido: $($_.FullName): $($Errors[0].Message)" }
    }

Write-Host 'CINEPULSE_RELEASE_TESTS_OK phase=9'
