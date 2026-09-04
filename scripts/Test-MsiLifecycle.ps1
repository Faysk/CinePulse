[CmdletBinding()]
param(
    [string]$Version = '1.1.1'
)

$ErrorActionPreference = 'Stop'
if ($env:CINEPULSE_CI_ALLOW_MSI_LIFECYCLE -ne '1') {
    throw 'Teste MSI lifecycle recusado fora de CI. Defina CINEPULSE_CI_ALLOW_MSI_LIFECYCLE=1 somente em runner descartável.'
}
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Msi = Join-Path $ProjectRoot "dist\CinePulse-$Version-Setup.msi"
if (-not (Test-Path -LiteralPath $Msi)) { throw "MSI não encontrado: $Msi" }

# Installer v2 must honor an arbitrary writable directory chosen by the user.
# The CI lifecycle uses a non-default root so a regression back to
# %LOCALAPPDATA%\Programs\CinePulse is observable.
$InstallParent = Join-Path $ProjectRoot 'artifacts\ci\msi-install-root'
$InstallRoot = Join-Path $InstallParent 'CinePulse'
$LogRoot = Join-Path $ProjectRoot 'artifacts\ci'
if (Test-Path -LiteralPath $InstallParent) { Remove-Item -LiteralPath $InstallParent -Recurse -Force }
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
    Invoke-Msi -Arguments @('/i', $Msi, "INSTALLFOLDER=$InstallRoot") -Name 'install'
    foreach ($Required in @('CinePulse-Installed.cmd', 'Install-CinePulse-Installed.cmd', 'pyproject.toml')) {
        if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot $Required))) {
            throw "Instalação MSI não criou $Required na pasta escolhida $InstallRoot"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $InstallRoot '.cinepulse-portable')) {
        throw 'Instalação MSI recriou indevidamente o marcador portátil.'
    }

    # Repair must preserve the custom destination and may not trigger bootstrap
    # downloads on this disposable runner.
    Invoke-Msi -Arguments @('/fa', $Msi) -Name 'repair'
    if (-not (Test-Path -LiteralPath (Join-Path $InstallRoot 'CinePulse-Installed.cmd'))) {
        throw 'Repair MSI não preservou o launcher na pasta escolhida.'
    }

    Invoke-Msi -Arguments @('/x', $Msi) -Name 'uninstall'
    if (Test-Path -LiteralPath (Join-Path $InstallRoot 'CinePulse-Installed.cmd')) {
        throw 'Uninstall MSI deixou o payload principal na pasta escolhida.'
    }
    Write-Host "CINEPULSE_MSI_LIFECYCLE_OK install=pass repair=pass uninstall=pass custom_root=$InstallRoot bootstrap=suppressed"
} finally {
    # Best-effort cleanup caso um estágio anterior falhe.
    if (Test-Path -LiteralPath $Msi) {
        $CleanupLog = Join-Path $LogRoot 'msi-cleanup.log'
        Start-Process msiexec.exe -ArgumentList @('/x', $Msi, '/qn', '/norestart', 'CINEPULSE_SKIP_BOOTSTRAP=1', '/L*v', $CleanupLog) -Wait -PassThru | Out-Null
    }
    if (Test-Path -LiteralPath $InstallParent) {
        Remove-Item -LiteralPath $InstallParent -Recurse -Force -ErrorAction SilentlyContinue
    }
}
