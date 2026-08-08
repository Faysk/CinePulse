[CmdletBinding()]
param(
    [string]$Version = '1.0.0-rc.4',
    [string]$Repository = '',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
& (Join-Path $PSScriptRoot 'Build-Portable.ps1') -Version $Version -Repository $Repository -SkipTests:$SkipTests
if (-not $?) { throw 'O pacote-base do MSI falhou.' }

$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$BuildRoot = Join-Path $RuntimeRoot 'msi-build'
$PayloadParent = Join-Path $BuildRoot 'payload'
$Payload = Join-Path $PayloadParent 'CinePulse'
$WixRoot = Join-Path $RuntimeRoot 'wix-6.0.2'
$WixExe = Join-Path $WixRoot 'wix.exe'
$BuildTools = Get-Content -LiteralPath (Join-Path $ProjectRoot 'installer\build-tools.json') -Raw | ConvertFrom-Json
$DotnetRoot = Join-Path $RuntimeRoot "dotnet-sdk-$($BuildTools.dotnet_sdk.version)"
$DotnetExe = Join-Path $DotnetRoot 'dotnet.exe'
$Archive = Join-Path $ProjectRoot "dist\CinePulse-$Version-windows-portable.zip"
$Output = Join-Path $ProjectRoot "dist\CinePulse-$Version-Setup.msi"

if (Test-Path -LiteralPath $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Path $PayloadParent -Force | Out-Null
Expand-Archive -LiteralPath $Archive -DestinationPath $PayloadParent -Force
if (-not (Test-Path -LiteralPath (Join-Path $Payload 'CinePulse.cmd'))) {
    throw 'O payload portátil não foi extraído corretamente.'
}

if (-not (Test-Path -LiteralPath $WixExe)) {
    if (-not (Test-Path -LiteralPath $DotnetExe)) {
        $SdkArchive = Join-Path $RuntimeRoot "dotnet-sdk-$($BuildTools.dotnet_sdk.version)-win-x64.zip"
        if (-not (Test-Path -LiteralPath $SdkArchive)) {
            Write-Host "Baixando SDK .NET $($BuildTools.dotnet_sdk.version) somente para compilar o MSI..."
            Invoke-WebRequest -UseBasicParsing -Uri $BuildTools.dotnet_sdk.url -OutFile "$SdkArchive.part"
            Move-Item -LiteralPath "$SdkArchive.part" -Destination $SdkArchive -Force
        }
        $ActualSdkHash = (Get-FileHash -Algorithm SHA512 -LiteralPath $SdkArchive).Hash.ToLowerInvariant()
        if ($ActualSdkHash -ne $BuildTools.dotnet_sdk.sha512.ToLowerInvariant()) {
            throw 'O SDK .NET de build não passou na verificação SHA-512.'
        }
        New-Item -ItemType Directory -Path $DotnetRoot -Force | Out-Null
        Expand-Archive -LiteralPath $SdkArchive -DestinationPath $DotnetRoot -Force
    }
    New-Item -ItemType Directory -Path $WixRoot -Force | Out-Null
    Write-Host "Baixando WiX Toolset $($BuildTools.wix.version) para o ambiente de build..."
    $env:DOTNET_CLI_HOME = Join-Path $RuntimeRoot 'dotnet-home'
    $env:DOTNET_NOLOGO = '1'
    $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
    & $DotnetExe tool install wix --tool-path $WixRoot --version $BuildTools.wix.version
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível instalar o WiX Toolset.' }
}

if (Test-Path -LiteralPath $Output) { Remove-Item -LiteralPath $Output -Force }
& $WixExe build (Join-Path $ProjectRoot 'installer\wix\Product.wxs') `
    -arch x64 -bindpath "Payload=$Payload" -out $Output
if ($LASTEXITCODE -ne 0) { throw 'A compilação do MSI falhou.' }
# O payload é deliberadamente per-user para que modelos e atualizações não exijam administrador.
# O harvester do WiX usa arquivos como KeyPath; ICE38/ICE91 não representam falha funcional nesse escopo.
& $WixExe msi validate -sice ICE38 -sice ICE64 -sice ICE91 $Output
if ($LASTEXITCODE -ne 0) { throw 'A validação do MSI falhou.' }

$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Output).Hash.ToLowerInvariant()
@{
    schema = 1
    version = $Version
    file = Split-Path -Leaf $Output
    sha256 = $Hash
    created_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ProjectRoot "dist\CinePulse-$Version-Setup-manifest.json") -Encoding UTF8

Remove-Item -LiteralPath $BuildRoot -Recurse -Force
Write-Host "CINEPULSE_MSI_BUILD_OK $Output"
Write-Host "SHA256 $Hash"
