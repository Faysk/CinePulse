[CmdletBinding(SupportsShouldProcess)]
param(
    [switch]$IncludeComponents
)

$ErrorActionPreference = 'Stop'
$Root = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'CinePulse' } else { Join-Path $HOME 'AppData\Local\CinePulse' }
if (-not (Test-Path -LiteralPath $Root)) {
    Write-Host 'CINEPULSE_USER_DATA_CLEANUP nothing-to-remove'
    exit 0
}

$Targets = @('cache', 'temp', 'runtime', 'logs')
if ($IncludeComponents) { $Targets += 'components' }
foreach ($Name in $Targets) {
    $Path = Join-Path $Root $Name
    if ((Test-Path -LiteralPath $Path) -and $PSCmdlet.ShouldProcess($Path, 'Remover dados gerados pelo CinePulse')) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}
Write-Host "CINEPULSE_USER_DATA_CLEANUP_OK root=$Root components=$IncludeComponents"
