[CmdletBinding()]
param(
    [string]$Version = '1.0.0-rc.3',
    [string]$Repository = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $ProjectRoot '.runtime\python\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Execute CinePulse.cmd uma vez antes de montar o pacote.' }
$env:PYTHONPATH = Join-Path $ProjectRoot 'src'
& (Join-Path $PSScriptRoot 'Test-Release.ps1')
if (-not $?) { throw 'O portão de release falhou.' }

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
    'pyproject.toml', 'requirements.lock'
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
    $Channel = [ordered]@{
        schema = 1
        manifest_url = "https://github.com/$Repository/releases/latest/download/cinepulse-update.json"
    }
    $Channel | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PackageRoot 'installer\update-channel.json') -Encoding UTF8
}

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
    $UpdateManifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Dist 'cinepulse-update.json') -Encoding UTF8
}
Remove-Item -LiteralPath $Staging -Recurse -Force

Write-Host "CINEPULSE_PORTABLE_BUILD_OK $Archive"
Write-Host "SHA256 $Hash"
