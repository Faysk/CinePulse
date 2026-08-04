[CmdletBinding()]
param(
    [switch]$Repair,
    [switch]$Diagnostics,
    [switch]$NonPortable,
    [switch]$ForcePortableRuntime,
    [switch]$ApplyUpdateOnly
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$VenvRoot = Join-Path $RuntimeRoot 'python'
$PythonExe = Join-Path $VenvRoot 'Scripts\python.exe'
$PortableMarker = Join-Path $ProjectRoot '.cinepulse-portable'
$InstallState = Join-Path $RuntimeRoot 'install-state.txt'
$BootstrapManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bootstrap-manifest.json') -Raw | ConvertFrom-Json
$UvExe = $null

function Apply-PendingUpdate {
    $PendingFile = Join-Path $RuntimeRoot 'pending-update.json'
    if (-not (Test-Path -LiteralPath $PendingFile)) { return }
    $Pending = Get-Content -LiteralPath $PendingFile -Raw | ConvertFrom-Json
    if ($Pending.schema -ne 1 -or -not $Pending.source -or -not $Pending.version) {
        throw 'A atualização pendente possui metadados inválidos.'
    }
    $UpdatesRoot = [IO.Path]::GetFullPath((Join-Path $RuntimeRoot 'updates'))
    $Source = [IO.Path]::GetFullPath([string]$Pending.source)
    $Prefix = $UpdatesRoot.TrimEnd('\') + '\'
    if (-not $Source.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A origem da atualização não pertence à pasta privada do CinePulse.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Source 'CinePulse.cmd')) -or
        -not (Test-Path -LiteralPath (Join-Path $Source 'pyproject.toml'))) {
        throw 'A atualização pendente está incompleta.'
    }

    $Backup = Join-Path $RuntimeRoot 'update-backup'
    if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }
    New-Item -ItemType Directory -Path $Backup -Force | Out-Null
    $RootFiles = @(
        '.env.example', '.gitattributes', '.gitignore', 'CHANGELOG.md', 'CONTRIBUTING.md',
        'CinePulse.cmd', 'cinepulse-files.json', 'LICENSE', 'README.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md',
        'pyproject.toml', 'requirements.lock'
    )
    $Directories = @('assets', 'docs', 'installer', 'src')
    try {
        foreach ($Name in $RootFiles) {
            $Current = Join-Path $ProjectRoot $Name
            if (Test-Path -LiteralPath $Current) { Copy-Item -LiteralPath $Current -Destination (Join-Path $Backup $Name) -Force }
        }
        foreach ($Name in $Directories) {
            $Current = Join-Path $ProjectRoot $Name
            if (Test-Path -LiteralPath $Current) { Copy-Item -LiteralPath $Current -Destination (Join-Path $Backup $Name) -Recurse -Force }
        }
        foreach ($Name in $RootFiles) {
            $Incoming = Join-Path $Source $Name
            if (Test-Path -LiteralPath $Incoming) { Copy-Item -LiteralPath $Incoming -Destination (Join-Path $ProjectRoot $Name) -Force }
        }
        foreach ($Name in $Directories) {
            $Incoming = Join-Path $Source $Name
            $Current = Join-Path $ProjectRoot $Name
            if (Test-Path -LiteralPath $Incoming) {
                if (Test-Path -LiteralPath $Current) { Remove-Item -LiteralPath $Current -Recurse -Force }
                Copy-Item -LiteralPath $Incoming -Destination $Current -Recurse -Force
            }
        }
        Remove-Item -LiteralPath $PendingFile -Force
        Remove-Item -LiteralPath (Split-Path -Parent (Split-Path -Parent $Source)) -Recurse -Force
        Remove-Item -LiteralPath $Backup -Recurse -Force
        Write-Host "CinePulse atualizado para $($Pending.version)."
    } catch {
        foreach ($Name in $RootFiles) {
            $Saved = Join-Path $Backup $Name
            if (Test-Path -LiteralPath $Saved) { Copy-Item -LiteralPath $Saved -Destination (Join-Path $ProjectRoot $Name) -Force }
        }
        foreach ($Name in $Directories) {
            $Saved = Join-Path $Backup $Name
            $Current = Join-Path $ProjectRoot $Name
            if (Test-Path -LiteralPath $Saved) {
                if (Test-Path -LiteralPath $Current) { Remove-Item -LiteralPath $Current -Recurse -Force }
                Copy-Item -LiteralPath $Saved -Destination $Current -Recurse -Force
            }
        }
        throw "A atualização falhou e a versão anterior foi restaurada. $($_.Exception.Message)"
    }
}

if (-not $NonPortable) {
    if (-not (Test-Path -LiteralPath $PortableMarker)) {
        New-Item -ItemType File -Path $PortableMarker -Force | Out-Null
    }
    $env:CINEPULSE_PORTABLE = '1'
}

Apply-PendingUpdate
if ($ApplyUpdateOnly) { exit 0 }

function Find-SystemPython {
    $Candidates = @('py', 'python')
    foreach ($Candidate in $Candidates) {
        $Command = Get-Command $Candidate -ErrorAction SilentlyContinue
        if ($Command) { return $Command.Source }
    }
    return $null
}

function Get-PortableUv {
    $BootstrapRoot = Join-Path $RuntimeRoot 'bootstrap'
    $UvExe = Join-Path $BootstrapRoot 'uv.exe'
    if (Test-Path -LiteralPath $UvExe) { return $UvExe }
    New-Item -ItemType Directory -Path $BootstrapRoot -Force | Out-Null
    $Archive = Join-Path $BootstrapRoot 'uv.zip.part'
    Write-Host "Baixando inicializador portátil uv $($BootstrapManifest.uv.version)..."
    Invoke-WebRequest -UseBasicParsing -Uri $BootstrapManifest.uv.url -OutFile $Archive
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    if ($ActualHash -ne $BootstrapManifest.uv.sha256.ToLowerInvariant()) {
        Remove-Item -LiteralPath $Archive -Force
        throw 'O download do inicializador portátil não passou na verificação SHA-256.'
    }
    $Extracted = Join-Path $BootstrapRoot 'extracted'
    if (Test-Path -LiteralPath $Extracted) { Remove-Item -LiteralPath $Extracted -Recurse -Force }
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
    $Found = Get-ChildItem -LiteralPath $Extracted -Recurse -File -Filter 'uv.exe' | Select-Object -First 1
    if (-not $Found) { throw 'O pacote do uv não contém o executável esperado.' }
    Move-Item -LiteralPath $Found.FullName -Destination $UvExe -Force
    Remove-Item -LiteralPath $Archive -Force
    Remove-Item -LiteralPath $Extracted -Recurse -Force
    return $UvExe
}

function Install-PortableFfmpeg {
    $ComponentsRoot = Join-Path $ProjectRoot 'components'
    $Destination = Join-Path $ComponentsRoot 'ffmpeg'
    $FfmpegExe = Join-Path $Destination 'bin\ffmpeg.exe'
    $FfprobeExe = Join-Path $Destination 'bin\ffprobe.exe'
    if ((Test-Path -LiteralPath $FfmpegExe) -and (Test-Path -LiteralPath $FfprobeExe)) { return }
    $StagingRoot = Join-Path $ComponentsRoot '.staging\ffmpeg'
    $Archive = Join-Path $StagingRoot 'ffmpeg.zip.part'
    $Extracted = Join-Path $StagingRoot 'extracted'
    New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null
    Write-Host "Baixando FFmpeg portátil $($BootstrapManifest.ffmpeg.version)..."
    Invoke-WebRequest -UseBasicParsing -Uri $BootstrapManifest.ffmpeg.url -OutFile $Archive
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    if ($ActualHash -ne $BootstrapManifest.ffmpeg.sha256.ToLowerInvariant()) {
        Remove-Item -LiteralPath $Archive -Force
        throw 'O download do FFmpeg não passou na verificação SHA-256.'
    }
    if (Test-Path -LiteralPath $Extracted) { Remove-Item -LiteralPath $Extracted -Recurse -Force }
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
    $FoundFfmpeg = Get-ChildItem -LiteralPath $Extracted -Recurse -File -Filter 'ffmpeg.exe' | Select-Object -First 1
    $FoundFfprobe = Get-ChildItem -LiteralPath $Extracted -Recurse -File -Filter 'ffprobe.exe' | Select-Object -First 1
    if (-not $FoundFfmpeg -or -not $FoundFfprobe) { throw 'O pacote não contém FFmpeg e FFprobe.' }
    $PackageRoot = Split-Path -Parent (Split-Path -Parent $FoundFfmpeg.FullName)
    $Incoming = Join-Path $StagingRoot 'incoming'
    if (Test-Path -LiteralPath $Incoming) { Remove-Item -LiteralPath $Incoming -Recurse -Force }
    Move-Item -LiteralPath $PackageRoot -Destination $Incoming
    $Previous = "$Destination.previous"
    if (Test-Path -LiteralPath $Previous) { Remove-Item -LiteralPath $Previous -Recurse -Force }
    if (Test-Path -LiteralPath $Destination) { Move-Item -LiteralPath $Destination -Destination $Previous }
    try {
        Move-Item -LiteralPath $Incoming -Destination $Destination
    } catch {
        if ((Test-Path -LiteralPath $Previous) -and -not (Test-Path -LiteralPath $Destination)) {
            Move-Item -LiteralPath $Previous -Destination $Destination
        }
        throw
    }
    if (Test-Path -LiteralPath $Previous) { Remove-Item -LiteralPath $Previous -Recurse -Force }
    Remove-Item -LiteralPath $StagingRoot -Recurse -Force
}

if ($Repair -and (Test-Path -LiteralPath $VenvRoot)) {
    $ResolvedRuntime = (Resolve-Path -LiteralPath $RuntimeRoot).Path
    $ResolvedVenv = (Resolve-Path -LiteralPath $VenvRoot).Path
    if (-not $ResolvedVenv.StartsWith($ResolvedRuntime, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'A pasta do ambiente não pertence ao CinePulse.'
    }
    Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    $SystemPython = if ($ForcePortableRuntime) { $null } else { Find-SystemPython }
    if ($SystemPython -and (Split-Path -Leaf $SystemPython) -eq 'py.exe') {
        & $SystemPython -3 -m venv $VenvRoot
    } elseif ($SystemPython) {
        & $SystemPython -m venv $VenvRoot
    } else {
        $UvExe = Get-PortableUv
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeRoot 'pythons'
        Write-Host "Instalando Python portátil $($BootstrapManifest.python.version)..."
        & $UvExe venv --python $BootstrapManifest.python.version --python-preference only-managed $VenvRoot
        if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar o Python portátil.' }
    }
}

$PythonVersionOk = & $PythonExe -c "import sys; print(int(sys.version_info >= (3, 11)))"
if ($PythonVersionOk.Trim() -ne '1') {
    throw 'O CinePulse requer Python 3.11 ou superior.'
}

$ProjectHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'pyproject.toml')).Hash
$LockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'requirements.lock')).Hash
$ExpectedState = "$ProjectHash`n$LockHash"
$CurrentState = if (Test-Path -LiteralPath $InstallState) { Get-Content -LiteralPath $InstallState -Raw } else { '' }
if ($Repair -or $CurrentState.Trim() -ne $ExpectedState.Trim()) {
    & $PythonExe -m pip --version *> $null
    if ($LASTEXITCODE -eq 0) {
        & $PythonExe -m pip install --disable-pip-version-check --quiet --requirement (Join-Path $ProjectRoot 'requirements.lock')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências do CinePulse.' }
        & $PythonExe -m pip install --disable-pip-version-check --quiet --no-deps --editable $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o CinePulse no ambiente privado.' }
    } else {
        if (-not $UvExe) { $UvExe = Get-PortableUv }
        & $UvExe pip install --python $PythonExe --quiet --requirement (Join-Path $ProjectRoot 'requirements.lock')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências com uv.' }
        & $UvExe pip install --python $PythonExe --quiet --no-deps --editable $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o CinePulse com uv.' }
    }
    Set-Content -LiteralPath $InstallState -Value $ExpectedState -Encoding UTF8
}

$PortableFfmpeg = Join-Path $ProjectRoot 'components\ffmpeg\bin\ffmpeg.exe'
$PortableFfprobe = Join-Path $ProjectRoot 'components\ffmpeg\bin\ffprobe.exe'
$SystemFfmpeg = Get-Command 'ffmpeg' -ErrorAction SilentlyContinue
$SystemFfprobe = Get-Command 'ffprobe' -ErrorAction SilentlyContinue
if ((-not $SystemFfmpeg -or -not $SystemFfprobe) -and
    (-not (Test-Path -LiteralPath $PortableFfmpeg) -or -not (Test-Path -LiteralPath $PortableFfprobe))) {
    Install-PortableFfmpeg
}

if ($Diagnostics) {
    & $PythonExe -m cinepulse.diagnostics
    exit $LASTEXITCODE
}

& $PythonExe -m cinepulse
exit $LASTEXITCODE
