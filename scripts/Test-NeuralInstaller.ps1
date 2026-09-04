[CmdletBinding()]
param(
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ManifestPath = Join-Path $Root 'installer\bootstrap-manifest.json'
$LockPath = Join-Path $Root 'requirements-neural.lock'
$InputPath = Join-Path $Root 'requirements-neural.in'
$InstallerPath = Join-Path $Root 'installer\Start-CinePulse.ps1'
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$TorchIndex = [string]$Manifest.demucs.torch_index
$TorchVersion = [string]$Manifest.demucs.torch_version
$SoundFileVersion = [string]$Manifest.demucs.soundfile_version

if (-not $TorchIndex.StartsWith('https://download.pytorch.org/whl/', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unexpected PyTorch index: $TorchIndex"
}
$InputText = Get-Content -LiteralPath $InputPath -Raw
if ($InputText -notmatch [regex]::Escape("--extra-index-url $TorchIndex")) {
    throw 'requirements-neural.in is not aligned with bootstrap torch_index.'
}
$LockText = Get-Content -LiteralPath $LockPath -Raw
foreach ($Pin in @("torch==$TorchVersion", "demucs==$($Manifest.demucs.version)", "soundfile==$SoundFileVersion")) {
    if ($LockText -notmatch [regex]::Escape($Pin)) { throw "requirements-neural.lock does not contain $Pin" }
}
if ($LockText -match '(?m)^torchaudio==') {
    throw 'Training-only torchaudio unexpectedly leaked into the CinePulse runtime lock.'
}
$InstallerText = Get-Content -LiteralPath $InstallerPath -Raw
if ($InstallerText -notmatch 'BootstrapManifest\.demucs\.torch_index' -or $InstallerText -notmatch '--index \$TorchIndex') {
    throw 'Start-CinePulse.ps1 does not route the neural lock through the manifest PyTorch index.'
}

if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
$Python = (Resolve-Path -LiteralPath $Python).Path
$TempRoot = Join-Path $Root ('temp\neural-resolve-' + [Guid]::NewGuid().ToString('N'))
$CacheRoot = Join-Path $Root 'cache\neural-resolver-ci'
$Venv = Join-Path $TempRoot 'venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$UvRoot = Join-Path $TempRoot 'uv'
$UvArchive = Join-Path $TempRoot 'uv.zip'

try {
    New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $CacheRoot -Force | Out-Null
    $env:TEMP = $TempRoot
    $env:TMP = $TempRoot
    $env:TMPDIR = $TempRoot
    $env:UV_CACHE_DIR = Join-Path $CacheRoot 'uv'
    $env:PIP_CACHE_DIR = Join-Path $CacheRoot 'pip'
    $env:TORCH_HOME = Join-Path $CacheRoot 'torch'
    $env:PYTHONNOUSERSITE = '1'

    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create neural resolver smoke venv.' }

    Invoke-WebRequest -UseBasicParsing -Uri $Manifest.uv.url -OutFile $UvArchive
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $UvArchive).Hash.ToLowerInvariant()
    if ($ActualHash -ne ([string]$Manifest.uv.sha256).ToLowerInvariant()) {
        throw 'Portable uv checksum mismatch in neural resolver smoke.'
    }
    Expand-Archive -LiteralPath $UvArchive -DestinationPath $UvRoot -Force
    $UvExe = (Get-ChildItem -LiteralPath $UvRoot -Recurse -File -Filter 'uv.exe' | Select-Object -First 1).FullName
    if (-not $UvExe) { throw 'uv.exe not found in portable uv archive.' }

    $PythonVersion = (& $VenvPython -c 'import platform; print(platform.python_version())').Trim()
    Write-Host "CINEPULSE_NEURAL_RESOLVE python=$PythonVersion torch=$TorchVersion index=$TorchIndex"
    $Output = & $UvExe pip install --python $VenvPython --require-hashes --index $TorchIndex -r $LockPath --dry-run 2>&1
    $Exit = $LASTEXITCODE
    $Output | ForEach-Object { Write-Host $_ }
    if ($Exit -ne 0) { throw "Neural lock dry-run failed with exit code $Exit." }
    Write-Host 'CINEPULSE_NEURAL_INSTALLER_RESOLVE_OK isolation=project-root'
}
finally {
    if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue }
}
