[CmdletBinding()]
param(
    [string]$Version = '1.0.0',
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
        $Channel = @{
            schema = 2
            manifest_url = "https://github.com/$Repository/releases/latest/download/cinepulse-update.json"
            manifest_signature_url = "https://github.com/$Repository/releases/latest/download/cinepulse-update.json.minisig"
            public_key = $MinisignPublicKey
            require_signature = $true
        }
        $Channel | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PackageRoot 'installer\update-channel.json') -Encoding UTF8
    } else {
        $Channel = @{ schema = 1; manifest_url = '' }
        $Channel | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PackageRoot 'installer\update-channel.json') -Encoding UTF8
    }
}

$Manifest = @{
    schema = 1
    version = $Version
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    files = @()
}
Get-ChildItem -LiteralPath $PackageRoot -File -Recurse | ForEach-Object {
    $Relative = [IO.Path]::GetRelativePath($PackageRoot, $_.FullName).Replace('\', '/')
    $Manifest.files += @{
        path = $Relative
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        size = $_.Length
    }
}
$ManifestPath = Join-Path $PackageRoot 'cinepulse-files.json'
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

if (Test-Path -LiteralPath $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -LiteralPath (Join-Path $PackageRoot '*') -DestinationPath $Archive -CompressionLevel Optimal

if ($MinisignSecretKey) {
    if (-not $MinisignExe -or -not (Test-Path -LiteralPath $MinisignExe)) { throw 'Assinatura exige -MinisignExe válido.' }
    & $MinisignExe -S -s $MinisignSecretKey -m $Archive
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao assinar o pacote portátil.' }
}

Write-Host "CINEPULSE_PORTABLE_BUILD_OK $Archive"
