[CmdletBinding()]
param(
    [string]$Version = '1.1.2',
    [string]$Repository = '',
    [string]$MinisignPublicKey = '',
    [string]$MinisignSecretKey = '',
    [string]$MinisignExe = '',
    [string]$SignTool = '',
    [string]$CertificateThumbprint = '',
    [string]$TimestampUrl = 'http://timestamp.digicert.com',
    [string]$BuildPython = '',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
function ConvertTo-MsiVersion {
    param([Parameter(Mandatory)][string]$SemanticVersion)
    $Clean = $SemanticVersion.Trim().TrimStart('v')
    if ($Clean -notmatch '^(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)(?:[-.]?(?<stage>alpha|a|beta|b|rc)[.]?(?<serial>\d+)?)?$') {
        throw "Versão SemVer incompatível com MSI: $SemanticVersion"
    }
    $Major = [int]$Matches.major
    $Minor = [int]$Matches.minor
    $Patch = [int]$Matches.patch
    $Stage = $Matches.stage
    $Serial = if ($Matches.serial) { [int]$Matches.serial } else { 0 }
    $Channel = switch -Regex ($Stage) {
        '^(alpha|a)$' { 100 + [Math]::Min($Serial, 99); break }
        '^(beta|b)$' { 300 + [Math]::Min($Serial, 99); break }
        '^rc$' { 500 + [Math]::Min($Serial, 99); break }
        default { 900 }
    }
    $Build = ($Patch * 1000) + $Channel
    if ($Major -gt 255 -or $Minor -gt 255 -or $Build -gt 65535) { throw 'Versão excede os limites do Windows Installer.' }
    return "$Major.$Minor.$Build"
}

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
& (Join-Path $PSScriptRoot 'Build-Portable.ps1') -Version $Version -Repository $Repository -MinisignPublicKey $MinisignPublicKey -MinisignSecretKey $MinisignSecretKey -MinisignExe $MinisignExe -BuildPython $BuildPython -SkipTests:$SkipTests
if (-not $?) { throw 'O pacote-base do MSI falhou.' }

$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$BuildRoot = Join-Path $RuntimeRoot 'msi-build'
$PayloadParent = Join-Path $BuildRoot 'payload'
$Payload = Join-Path $PayloadParent 'CinePulse'
$WixRoot = Join-Path $RuntimeRoot 'wix-6.0.2'
$WixExe = Join-Path $WixRoot 'wix.exe'
$WixExtensionCache = Join-Path $RuntimeRoot 'wix-extension-cache'
$BuildTools = Get-Content -LiteralPath (Join-Path $ProjectRoot 'installer\build-tools.json') -Raw | ConvertFrom-Json
$DotnetRoot = Join-Path $RuntimeRoot "dotnet-sdk-$($BuildTools.dotnet_sdk.version)"
$DotnetExe = Join-Path $DotnetRoot 'dotnet.exe'
$WixUiExtension = "WixToolset.UI.wixext/$($BuildTools.wix.version)"
$Archive = Join-Path $ProjectRoot "dist\CinePulse-$Version-windows-portable.zip"
$Output = Join-Path $ProjectRoot "dist\CinePulse-$Version-Setup.msi"

if (Test-Path -LiteralPath $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Path $PayloadParent -Force | Out-Null
Expand-Archive -LiteralPath $Archive -DestinationPath $PayloadParent -Force
if (-not (Test-Path -LiteralPath (Join-Path $Payload 'CinePulse.cmd'))) {
    throw 'O payload portátil não foi extraído corretamente.'
}
$PortableMarker = Join-Path $Payload '.cinepulse-portable'
if (Test-Path -LiteralPath $PortableMarker) { Remove-Item -LiteralPath $PortableMarker -Force }
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'CinePulse-Installed.cmd') -Destination (Join-Path $Payload 'CinePulse-Installed.cmd') -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'Install-CinePulse-Installed.cmd') -Destination (Join-Path $Payload 'Install-CinePulse-Installed.cmd') -Force
if (-not (Test-Path -LiteralPath (Join-Path $Payload 'assets\cinepulse.ico'))) { throw 'Ícone Windows ausente do payload MSI.' }
$MsiVersion = ConvertTo-MsiVersion -SemanticVersion $Version
$IntegrityFiles = [ordered]@{}
Get-ChildItem -LiteralPath $Payload -File -Recurse | Sort-Object FullName | ForEach-Object {
    $Relative = $_.FullName.Substring($Payload.Length + 1).Replace('\', '/')
    if ($Relative -ne 'cinepulse-files.json') {
        $IntegrityFiles[$Relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    }
}
[ordered]@{ schema = 1; files = $IntegrityFiles } | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $Payload 'cinepulse-files.json') -Encoding UTF8

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

# The install-directory wizard lives in WixToolset.UI.wixext. Keep the
# extension cache inside CinePulse build runtime instead of the user profile.
New-Item -ItemType Directory -Path $WixExtensionCache -Force | Out-Null
$env:WIX_EXTENSION = $WixExtensionCache
& $WixExe extension add -g $WixUiExtension
if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar a extensão de UI do WiX.' }

if (Test-Path -LiteralPath $Output) { Remove-Item -LiteralPath $Output -Force }
& $WixExe build (Join-Path $ProjectRoot 'installer\wix\Product.wxs') `
    -arch x64 -ext $WixUiExtension -bindpath "Payload=$Payload" -d ProductVersion=$MsiVersion -out $Output
if ($LASTEXITCODE -ne 0) { throw 'A compilação do MSI falhou.' }
# O payload é deliberadamente per-user para que modelos e atualizações não exijam administrador.
# O harvester do WiX usa arquivos como KeyPath; ICE38/ICE91 não representam falha funcional nesse escopo.
& $WixExe msi validate -sice ICE38 -sice ICE64 -sice ICE91 $Output
if ($LASTEXITCODE -ne 0) { throw 'A validação do MSI falhou.' }

$AuthenticodeSigned = $false
if ($CertificateThumbprint) {
    if (-not $SignTool -or -not (Test-Path -LiteralPath $SignTool)) { throw 'Assinatura Authenticode solicitada, mas -SignTool não aponta para signtool.exe.' }
    & $SignTool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $Output
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao assinar o MSI com Authenticode.' }
    & $SignTool verify /pa /v $Output
    if ($LASTEXITCODE -ne 0) { throw 'A assinatura Authenticode do MSI não passou na verificação.' }
    $AuthenticodeSigned = $true
} else {
    Write-Warning 'MSI gerado sem Authenticode: nenhum certificado foi fornecido.'
}
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Output).Hash.ToLowerInvariant()
@{
    schema = 1
    version = $Version
    msi_version = $MsiVersion
    authenticode_signed = $AuthenticodeSigned
    file = Split-Path -Leaf $Output
    sha256 = $Hash
    created_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $ProjectRoot "dist\CinePulse-$Version-Setup-manifest.json") -Encoding UTF8

Remove-Item -LiteralPath $BuildRoot -Recurse -Force
Write-Host "CINEPULSE_MSI_BUILD_OK $Output"
Write-Host "SHA256 $Hash"
