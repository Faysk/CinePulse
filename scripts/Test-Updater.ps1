[CmdletBinding()]
param(
    [string]$Version = '1.1.0'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot '.runtime'))
$SmokeRoot = [IO.Path]::GetFullPath((Join-Path $RuntimeRoot 'updater-smoke'))
if (-not $SmokeRoot.StartsWith($RuntimeRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destino de teste fora do ambiente privado.'
}
$Archive = Join-Path $ProjectRoot "dist\CinePulse-$Version-windows-portable.zip"
if (-not (Test-Path -LiteralPath $Archive)) { throw 'Monte o pacote antes do teste do atualizador.' }
if (Test-Path -LiteralPath $SmokeRoot) { Remove-Item -LiteralPath $SmokeRoot -Recurse -Force }

try {
    $TargetParent = Join-Path $SmokeRoot 'target-parent'
    $IncomingParent = Join-Path $SmokeRoot 'incoming-parent'
    Expand-Archive -LiteralPath $Archive -DestinationPath $TargetParent
    Expand-Archive -LiteralPath $Archive -DestinationPath $IncomingParent
    $Target = Join-Path $TargetParent 'CinePulse'
    $IncomingOriginal = Join-Path $IncomingParent 'CinePulse'
    $Stage = Join-Path $Target ".runtime\updates\$Version\extracted\CinePulse"
    New-Item -ItemType Directory -Path (Split-Path -Parent $Stage) -Force | Out-Null
    Move-Item -LiteralPath $IncomingOriginal -Destination $Stage
    New-Item -ItemType Directory -Path (Join-Path $Target 'data') -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $Target 'data\preserve-me.txt') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $Target '.runtime') -Force | Out-Null
    @{ schema = 1; version = $Version; source = $Stage } | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $Target '.runtime\pending-update.json') -Encoding UTF8

    & (Join-Path $Target 'installer\Start-CinePulse.ps1') -ApplyUpdateOnly
    if (-not $?) { throw 'Aplicação isolada falhou.' }
    if (-not (Test-Path -LiteralPath (Join-Path $Target 'data\preserve-me.txt'))) {
        throw 'A atualização não preservou os dados mutáveis.'
    }
    if (Test-Path -LiteralPath (Join-Path $Target '.runtime\pending-update.json')) {
        throw 'O marcador de atualização não foi removido.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Target 'cinepulse-files.json'))) {
        throw 'O manifesto de integridade não foi aplicado.'
    }
    Write-Host 'CINEPULSE_UPDATE_APPLY_SMOKE_OK mutable-data=preserved'
} finally {
    if (Test-Path -LiteralPath $SmokeRoot) { Remove-Item -LiteralPath $SmokeRoot -Recurse -Force }
}
