[CmdletBinding()]
param(
    [string]$Version = '1.0.0-rc.6'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot '.runtime'))
$SmokeRoot = [IO.Path]::GetFullPath((Join-Path $RuntimeRoot 'msi-smoke'))
if (-not $SmokeRoot.StartsWith($RuntimeRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Destino de teste fora do ambiente privado.'
}
$Msi = Join-Path $ProjectRoot "dist\CinePulse-$Version-Setup.msi"
if (-not (Test-Path -LiteralPath $Msi)) { throw 'MSI não encontrado.' }
if (Test-Path -LiteralPath $SmokeRoot) { Remove-Item -LiteralPath $SmokeRoot -Recurse -Force }
New-Item -ItemType Directory -Path $SmokeRoot -Force | Out-Null
try {
    $Process = Start-Process msiexec.exe -ArgumentList @('/a', "`"$Msi`"", '/qn', "TARGETDIR=`"$SmokeRoot`"") -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw "A extração administrativa do MSI falhou: $($Process.ExitCode)." }
    $Launcher = Get-ChildItem -LiteralPath $SmokeRoot -Recurse -File -Filter 'CinePulse-Installed.cmd' | Select-Object -First 1
    $Installer = Get-ChildItem -LiteralPath $SmokeRoot -Recurse -File -Filter 'Install-CinePulse-Installed.cmd' | Select-Object -First 1
    $Bootstrap = Get-ChildItem -LiteralPath $SmokeRoot -Recurse -File -Filter 'bootstrap-manifest.json' | Select-Object -First 1
    if (-not $Launcher -or -not $Installer -or -not $Bootstrap) { throw 'O MSI não contém os inicializadores e o manifesto de instalação.' }
    $WixSource = Get-Content -LiteralPath (Join-Path $ProjectRoot 'installer\wix\Product.wxs') -Raw
    if ($WixSource -notmatch 'CinePulseDesktopShortcut' -or $WixSource -notmatch 'Install-CinePulse-Installed\.cmd' -or $WixSource -notmatch '\$\(var\.ProductVersion\)' -or $WixSource -notmatch 'CinePulseIcon') {
        throw 'O MSI não contém o contrato de atalho e instalação visível.'
    }
    Write-Host 'CINEPULSE_MSI_SMOKE_OK installed-launcher=present installer=nonportable desktop-shortcut=present icon=present dynamic-version=present bootstrap=present'
} finally {
    if (Test-Path -LiteralPath $SmokeRoot) { Remove-Item -LiteralPath $SmokeRoot -Recurse -Force }
}
