[CmdletBinding()]
param(
    [string]$Version = '1.0.0-rc.6',
    [string]$Repository = '',
    [string]$MinisignPublicKey = '',
    [string]$MinisignSecretKey = '',
    [string]$MinisignExe = '',
    [string]$BuildPython = '',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python = $BuildPython
if (-not $Python) {
    $ManagedBuildPython = Join-Path $ProjectRoot '.runtime\python\Scripts\python.exe'
    if (Test-Path -LiteralPath $ManagedBuildPython) {
        $Python = $ManagedBuildPython
    } else {
        $PythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
        if (-not $PythonCommand) { $PythonCommand = Get-Command 'py' -ErrorAction SilentlyContinue }
        if (-not $PythonCommand) { throw 'Python de build não encontrado. Use -BuildPython ou inicialize o runtime gerenciado.' }
        $Python = $PythonCommand.Source
    }
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Python de build inválido: $Python" }
$env:PYTHONPATH = Join-Path $ProjectRoot 'src'
if (-not $SkipTests) {
    & (Join-Path $PSScriptRoot 'Test-Release.ps1')
    if (-not $?) { throw 'O portão de release falhou.' }
}

$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$Staging = Join-Path $RuntimeRoot 'package-staging'
$PackageRoot = Join-Path $Staging 'CinePulse'
$Dist = Join-Path $ProjectRoot 'dist'
$Archive = Join-Path $Dist "CinePulse-$Version-windows-portable.zip"

if (Test-Path -LiteralPath $Staging) { Remove-Item -LiteralPath $Staging -Recurse -Force }
New-Item -ItemType Directory -Path $PackageRoot -Force | Out-Null
New-Item -ItemType Directory -Path $Dist -Force | Out-Null

$Files = @(
    '.env.example', '.gitattributes', '.gitignore', 'CHANGELOG.md', 'CONTRIBUTING.md',
    'CinePulse.cmd', 'Install-CinePulse.cmd', 'LICENSE', 'README.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md',
    'pyproject.toml', 'requirements.lock', 'requirements-neural.in', 'requirements-neural.lock'
)
$Directories = @('assets', 'docs', 'installer', 'src')
foreach ($File in $Files) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $File) -Destination (Join-Path $PackageRoot $File)
}
foreach ($Directory in $Directories) {
    Copy-Item -LiteralPath (Join-Path $ProjectRoot $Directory) -Destination (Join-Path $PackageRoot $Directory) -Recurse
}
Get-ChildItem -LiteralPath $PackageRoot -Directory -Recurse -Filter '__pycache__' |
    Sort-Object FullName -Descending |
    Remove-Item -Recurse -Force
Get-ChildItem -LiteralPath $PackageRoot -File -Recurse -Include '*.pyc','*.pyo' |
    Remove-Item -Force
New-Item -ItemType File -Path (Join-Path $PackageRoot '.cinepulse-portable') -Force | Out-Null

if ($Repository) {
    if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
        throw 'Use o formato dono/repositorio em -Repository.'
    }
    if ($MinisignPublicKey) {
        if (-not $MinisignExe -or -not (Test-Path -LiteralPath $MinisignExe)) { throw 'Canal assinado exige -MinisignExe válido.' }
        if (-not $MinisignSecretKey -or -not (Test-Path -LiteralPath $MinisignSecretKey)) { throw 'Canal assinado exige -MinisignSecretKey válido.' }
        $ToolsRoot = Join-Path $PackageRoot 'installer\tools'
        New-Item -ItemType Directory -Path $ToolsRoot -Force | Out-Null
        Copy-Item -LiteralPath $MinisignExe -Destination (Join-Path $ToolsRoot 'minisign.exe') -Force
        $Channel = [ordered]@{
            schema = 2
            manifest_url = "https://github.com/$Repository/releases/latest/download/cinepulse-update.json"
            require_signature = $true
            public_key = $MinisignPublicKey.Trim()
            manifest_signature_url = "https://github.com/$Repository/releases/latest/download/cinepulse-update.json.minisig"
        }
    } else {
        $Channel = [ordered]@{
            schema = 1
            manifest_url = "https://github.com/$Repository/releases/latest/download/cinepulse-update.json"
        }
    }
    $Channel | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PackageRoot 'installer\update-channel.json') -Encoding UTF8
}

& $Python (Join-Path $ProjectRoot 'scripts\generate_sbom.py') --output (Join-Path $PackageRoot 'sbom.cdx.json')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o SBOM CycloneDX.' }

$IntegrityFiles = [ordered]@{}
Get-ChildItem -LiteralPath $PackageRoot -File -Recurse | Sort-Object FullName | ForEach-Object {
    $Relative = $_.FullName.Substring($PackageRoot.Length + 1).Replace('\', '/')
    if ($Relative -ne 'cinepulse-files.json') {
        $IntegrityFiles[$Relative] = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    }
}
[ordered]@{ schema = 1; files = $IntegrityFiles } | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $PackageRoot 'cinepulse-files.json') -Encoding UTF8

if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -LiteralPath $PackageRoot -DestinationPath $Archive -CompressionLevel Optimal
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
$Manifest = [ordered]@{
    schema = 1
    version = $Version
    file = Split-Path -Leaf $Archive
    sha256 = $Hash
    created_at = (Get-Date).ToUniversalTime().ToString('o')
}
$ManifestPath = Join-Path $Dist "CinePulse-$Version-manifest.json"
$Manifest | ConvertTo-Json | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
if ($Repository) {
    $UpdateManifest = [ordered]@{
        schema = 1
        version = $Version
        download_url = "https://github.com/$Repository/releases/download/v$Version/$(Split-Path -Leaf $Archive)"
        sha256 = $Hash
        notes_url = "https://github.com/$Repository/releases/tag/v$Version"
    }
    $UpdateManifestPath = Join-Path $Dist 'cinepulse-update.json'
    $UpdateManifest | ConvertTo-Json | Set-Content -LiteralPath $UpdateManifestPath -Encoding UTF8
    if ($MinisignPublicKey) {
        $SignaturePath = "$UpdateManifestPath.minisig"
        & $MinisignExe -S -s $MinisignSecretKey -m $UpdateManifestPath -x $SignaturePath -q
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $SignaturePath)) { throw 'Falha ao assinar o manifesto de atualização com Minisign.' }
    }
}
Remove-Item -LiteralPath $Staging -Recurse -Force

Write-Host "CINEPULSE_PORTABLE_BUILD_OK $Archive"
Write-Host "SHA256 $Hash"
