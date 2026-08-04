[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$DataRoot = Join-Path $ProjectRoot 'data'
if (-not (Test-Path -LiteralPath $DataRoot)) {
    Write-Host 'Nenhum artefato de teste encontrado.'
    exit 0
}
$ResolvedData = (Resolve-Path -LiteralPath $DataRoot).Path
$Targets = Get-ChildItem -LiteralPath $ResolvedData -Directory | Where-Object {
    $_.Name -eq 'test-runs' -or $_.Name -like 'package-smoke-*'
}
foreach ($Target in $Targets) {
    $ResolvedTarget = (Resolve-Path -LiteralPath $Target.FullName).Path
    if (-not $ResolvedTarget.StartsWith($ResolvedData + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Destino recusado: $ResolvedTarget"
    }
    if ($Target.Name -ne 'test-runs' -and $Target.Name -notlike 'package-smoke-*') {
        throw "Nome de artefato recusado: $($Target.Name)"
    }
    Remove-Item -LiteralPath $ResolvedTarget -Recurse -Force
    Write-Host "Removido: $ResolvedTarget"
}
Write-Host 'CINEPULSE_TEST_ARTIFACTS_CLEAN'

