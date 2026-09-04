[CmdletBinding()]
param(
    [string]$Version = '1.0.0'
)

$ErrorActionPreference = 'Stop'
if ($env:CINEPULSE_CI_ALLOW_MSI_LIFECYCLE -ne '1') {
    throw 'Teste MSI lifecycle recusado fora de CI. Defina CINEPULSE_CI_ALLOW_MSI_LIFECYCLE=1 somente em runner descartável.'
}
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Msi = Join-Path $ProjectRoot "dist\CinePulse-$Version-Setup.msi"
if (-not (Test-Path -LiteralPath $Msi)) { throw "MSI não encontrado: $Msi" }
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\CinePulse'
$LogRoot = Join-Path $ProjectRoot 'artifacts\ci'
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

function Invoke-Msi {
    param([Parameter(Mandatory)][string[]]$Arguments, [Parameter(Mandatory)][string]$Name)
    $Log = Join-Path $LogRoot "msi-$Name.log"
    $All = @($Arguments + @('/qn', '/norestart', 'CINEPULSE_SKIP_BOOTSTRAP=1', '/L*v', $Log))
    $Process = Start-Process msiexec.exe -ArgumentList $All -Wait -PassThru
    if ($Process.ExitCode -notin @(0, 3010)) {
        throw "MSI $Name falhou com código $($Process.ExitCode). Consulte $Log"
    }
}

try {
    Invoke-Msi -Arguments @('/i', $Msi) -Name 'install'
    foreach ($Required in @('CinePulse-Installed.cmd', 'Install-CinePulse-Installed.cmd', 'pyproject.toml')) {
        if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot $Required))) {
            throw "Instalação MSI não criou $Required em $InstallRoot"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $InstallRoot '.cinepulse-portable')) {
        throw 'Instalação MSI recriou indevidamente o marcador portátil.'
    }

    # Repair precisa ser seguro e não pode disparar bootstrap/download no runner.
    Invoke-Msi -Arguments @('/fa', $Msi) -Name 'repair'
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'CinePulse-Installed.cmd'))) {
        throw 'Repair MSI removeu o launcher instalado.'
    }

    Invoke-Msi -Arguments @('/x', $Msi) -Name 'uninstall'
    if (Test-Path -LiteralPath (Join-Path $InstallRoot 'CinePulse-Installed.cmd')) {
        throw 'Uninstall MSI deixou o payload principal instalado.'
    }
    Write-Host 'CINEPULSE_MSI_LIFECYCLE_OK install=pass repair=pass uninstall=pass bootstrap=suppressed'
} finally {
    # Best-effort cleanup caso um estágio anterior falhe.
    if (Test-Path -LiteralPath $Msi) {
        $CleanupLog = Join-Path $LogRoot 'msi-cleanup.log'
        Start-Process msiexec.exe -ArgumentList @('/x', $Msi, '/qn', '/norestart', 'CINEPULSE_SKIP_BOOTSTRAP=1', '/L*v', $CleanupLog) -Wait -PassThru | Out-Null
    }
}
