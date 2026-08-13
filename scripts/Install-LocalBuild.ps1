[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Target,
    [string]$Version = '1.0.0-rc.6'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$ResolvedTarget = (Resolve-Path -LiteralPath $Target).Path
if (-not (Test-Path -LiteralPath (Join-Path $ResolvedTarget 'CinePulse.cmd')) -or
    -not (Test-Path -LiteralPath (Join-Path $ResolvedTarget '.cinepulse-portable'))) {
    throw 'O destino não parece ser uma instalação portátil do CinePulse.'
}
$Archive = Join-Path $ProjectRoot "dist\CinePulse-$Version-windows-portable.zip"
$ManifestPath = Join-Path $ProjectRoot "dist\CinePulse-$Version-manifest.json"
if (-not (Test-Path -LiteralPath $Archive) -or -not (Test-Path -LiteralPath $ManifestPath)) {
    throw 'Monte o pacote portátil antes de instalar a build local.'
}
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
if ($ActualHash -ne $Manifest.sha256.ToLowerInvariant()) {
    throw 'O ZIP local não corresponde ao manifesto SHA-256.'
}

$RuntimeRoot = Join-Path $ResolvedTarget '.runtime'
$VersionRoot = Join-Path $RuntimeRoot "updates\$Version"
$Extracted = Join-Path $VersionRoot 'extracted'
if (Test-Path -LiteralPath $VersionRoot) { Remove-Item -LiteralPath $VersionRoot -Recurse -Force }
New-Item -ItemType Directory -Path $Extracted -Force | Out-Null
Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
$Source = Join-Path $Extracted 'CinePulse'
if (-not (Test-Path -LiteralPath (Join-Path $Source 'CinePulse.cmd'))) {
    throw 'O pacote local não possui a estrutura esperada.'
}
@{ schema = 1; version = $Version; source = $Source } | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $RuntimeRoot 'pending-update.json') -Encoding UTF8

& (Join-Path $ResolvedTarget 'installer\Start-CinePulse.ps1') -ApplyUpdateOnly
if (-not $?) { throw 'A atualização local falhou.' }
$VersionText = Get-Content -LiteralPath (Join-Path $ResolvedTarget 'src\cinepulse\__init__.py') -Raw
if ($VersionText -notmatch [regex]::Escape($Version)) { throw 'A versão instalada não foi confirmada.' }
Write-Host "CINEPULSE_LOCAL_BUILD_INSTALLED version=$Version target=$ResolvedTarget"
