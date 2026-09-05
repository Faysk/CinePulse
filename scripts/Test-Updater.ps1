[CmdletBinding()]
param(
    [string]$Version = '1.1.2'
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

    # Simulate an older payload and a future release introducing a brand-new
    # managed root file. A failed update must restore the old file and remove
    # the new one, otherwise the installation becomes a mixed-version tree.
    $OldReadme = 'CINEPULSE_OLD_PAYLOAD_SENTINEL'
    Set-Content -LiteralPath (Join-Path $Target 'README.md') -Value $OldReadme -Encoding UTF8
    $FutureFile = Join-Path $IncomingOriginal 'future-root-file.txt'
    Set-Content -LiteralPath $FutureFile -Value 'CINEPULSE_FUTURE_FILE' -Encoding UTF8
    $IncomingManifestPath = Join-Path $IncomingOriginal 'cinepulse-files.json'
    $IncomingManifest = Get-Content -LiteralPath $IncomingManifestPath -Raw | ConvertFrom-Json
    $FutureInfo = Get-Item -LiteralPath $FutureFile
    $FutureEntry = [pscustomobject]@{
        path = 'future-root-file.txt'
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $FutureFile).Hash.ToLowerInvariant()
        size = $FutureInfo.Length
    }
    $IncomingManifest.files = @($IncomingManifest.files) + @($FutureEntry)
    $IncomingManifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $IncomingManifestPath -Encoding UTF8

    $Stage = Join-Path $Target ".runtime\updates\$Version\extracted\CinePulse"
    New-Item -ItemType Directory -Path (Split-Path -Parent $Stage) -Force | Out-Null
    Move-Item -LiteralPath $IncomingOriginal -Destination $Stage
    New-Item -ItemType Directory -Path (Join-Path $Target 'data') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $Target 'data\preserve-me.txt') -Value 'mutable' -Encoding UTF8
    New-Item -ItemType Directory -Path (Join-Path $Target '.runtime') -Force | Out-Null
    $Pending = Join-Path $Target '.runtime\pending-update.json'
    @{ schema = 1; version = $Version; source = $Stage } | ConvertTo-Json |
        Set-Content -LiteralPath $Pending -Encoding UTF8

    $env:CINEPULSE_CI_UPDATE_FAIL_AFTER_COPY = '1'
    $FailureObserved = $false
    try {
        & (Join-Path $Target 'installer\Start-CinePulse.ps1') -ApplyUpdateOnly
    } catch {
        $FailureObserved = $true
        Write-Host "CINEPULSE_UPDATE_FAULT_OBSERVED $($_.Exception.Message)"
    } finally {
        Remove-Item Env:CINEPULSE_CI_UPDATE_FAIL_AFTER_COPY -ErrorAction SilentlyContinue
    }
    if (-not $FailureObserved) { throw 'A falha injetada no atualizador não foi observada.' }
    if ((Get-Content -LiteralPath (Join-Path $Target 'README.md') -Raw).Trim() -ne $OldReadme) {
        throw 'Rollback não restaurou o payload anterior.'
    }
    if (Test-Path -LiteralPath (Join-Path $Target 'future-root-file.txt')) {
        throw 'Rollback deixou arquivo pertencente somente à nova versão.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Target 'data\preserve-me.txt'))) {
        throw 'Rollback removeu dado mutável do usuário.'
    }
    if (-not (Test-Path -LiteralPath $Pending)) {
        throw 'Rollback removeu o marcador pendente necessário para retry.'
    }
    if (-not (Test-Path -LiteralPath $Stage)) {
        throw 'Rollback removeu a origem necessária para retry.'
    }
    Write-Host 'CINEPULSE_UPDATE_ROLLBACK_FAULT_OK old=restored future=removed mutable=preserved pending=kept'

    & (Join-Path $Target 'installer\Start-CinePulse.ps1') -ApplyUpdateOnly
    if (-not $?) { throw 'Aplicação isolada falhou.' }
    if (-not (Test-Path -LiteralPath (Join-Path $Target 'data\preserve-me.txt'))) {
        throw 'A atualização não preservou os dados mutáveis.'
    }
    if (Test-Path -LiteralPath $Pending) {
        throw 'O marcador de atualização não foi removido.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Target 'cinepulse-files.json'))) {
        throw 'O manifesto de integridade não foi aplicado.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Target 'future-root-file.txt'))) {
        throw 'A atualização final não aplicou arquivo novo gerenciado.'
    }
    if ((Get-Content -LiteralPath (Join-Path $Target 'README.md') -Raw).Trim() -eq $OldReadme) {
        throw 'A atualização final manteve arquivo obsoleto do payload anterior.'
    }
    Write-Host 'CINEPULSE_UPDATE_APPLY_SMOKE_OK mutable-data=preserved managed-tree=replaced'
} finally {
    Remove-Item Env:CINEPULSE_CI_UPDATE_FAIL_AFTER_COPY -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $SmokeRoot) { Remove-Item -LiteralPath $SmokeRoot -Recurse -Force }
}
