[CmdletBinding()]
param(
    [switch]$Repair,
    [switch]$Diagnostics,
    [switch]$NonPortable,
    [switch]$ForcePortableRuntime,
    [switch]$ApplyUpdateOnly,
    [switch]$CoreOnly,
    [switch]$InstallOnly,
    [string]$ComponentsCsv = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PortableMarker = Join-Path $ProjectRoot '.cinepulse-portable'

# Installer v2: installed and portable modes are both self-contained.  The
# chosen CinePulse directory owns runtime, components, mutable data, caches and
# all temporary files.  Windows itself (and an NVIDIA display driver when GPU
# acceleration is desired) is the only external runtime dependency.
$RuntimeRoot = Join-Path $ProjectRoot '.runtime'
$ComponentsRoot = Join-Path $ProjectRoot 'components'
$DataRoot = Join-Path $ProjectRoot 'data'
$CacheRoot = Join-Path $ProjectRoot 'cache'
$TempRoot = Join-Path $ProjectRoot 'temp'
$VenvRoot = Join-Path $RuntimeRoot 'python'
$PythonExe = Join-Path $VenvRoot 'Scripts\python.exe'
$InstallState = Join-Path $RuntimeRoot 'install-state.txt'
$BootstrapManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bootstrap-manifest.json') -Raw | ConvertFrom-Json
$UvExe = $null
$TranscriptStarted = $false

foreach ($Directory in @(
    $RuntimeRoot, $ComponentsRoot, $DataRoot, $CacheRoot, $TempRoot,
    (Join-Path $DataRoot 'logs'), (Join-Path $CacheRoot 'uv'),
    (Join-Path $CacheRoot 'pip'), (Join-Path $CacheRoot 'torch'),
    (Join-Path $CacheRoot 'huggingface'), (Join-Path $CacheRoot 'numba'),
    (Join-Path $CacheRoot 'matplotlib'), (Join-Path $CacheRoot 'pycache')
)) {
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
}

$env:CINEPULSE_ROOT = $ProjectRoot
$env:CINEPULSE_DATA_DIR = $DataRoot
$env:CINEPULSE_COMPONENTS_DIR = $ComponentsRoot
$env:CINEPULSE_CACHE_DIR = $CacheRoot
$env:CINEPULSE_TEMP_DIR = $TempRoot
$env:TEMP = $TempRoot
$env:TMP = $TempRoot
$env:TMPDIR = $TempRoot
$env:UV_CACHE_DIR = Join-Path $CacheRoot 'uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeRoot 'pythons'
$env:PIP_CACHE_DIR = Join-Path $CacheRoot 'pip'
$env:TORCH_HOME = Join-Path $CacheRoot 'torch'
$env:XDG_CACHE_HOME = Join-Path $CacheRoot 'xdg'
$env:HF_HOME = Join-Path $CacheRoot 'huggingface'
$env:NUMBA_CACHE_DIR = Join-Path $CacheRoot 'numba'
$env:MPLCONFIGDIR = Join-Path $CacheRoot 'matplotlib'
$env:PYTHONPYCACHEPREFIX = Join-Path $CacheRoot 'pycache'
$env:PYTHONNOUSERSITE = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$RequestedComponents = @($ComponentsCsv.Split(',', [StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $_.Trim().ToLowerInvariant() })
$AllowedComponents = @('ffmpeg', 'real-esrgan', 'rife', 'demucs')
foreach ($Requested in $RequestedComponents) {
    if ($Requested -notin $AllowedComponents) { throw "Componente desconhecido: $Requested" }
}

if ($InstallOnly) {
    try { $Host.UI.RawUI.WindowTitle = 'CinePulse - Instalando componentes locais' } catch { }
    $InstallerLog = Join-Path $DataRoot 'logs\installer.log'
    New-Item -ItemType Directory -Path (Split-Path -Parent $InstallerLog) -Force | Out-Null
    try {
        Start-Transcript -LiteralPath $InstallerLog -Append | Out-Null
        $TranscriptStarted = $true
    } catch {
        Write-Warning "Não foi possível iniciar o log permanente: $($_.Exception.Message)"
    }
    $InstallMode = if ($RequestedComponents.Count) { $RequestedComponents -join ',' } else { 'completo' }
    Write-Host "CINEPULSE_INSTALL_START componentes=$InstallMode"
    Write-Host "Pasta do programa: $ProjectRoot"
}

function Apply-PendingUpdate {
    $Applier = Join-Path $PSScriptRoot 'Apply-CinePulseUpdate.ps1'
    if (-not (Test-Path -LiteralPath $Applier)) { throw 'Aplicador transacional de atualização não encontrado.' }
    try {
        & $Applier -ProjectRoot $ProjectRoot -RuntimeRoot $RuntimeRoot
    } catch {
        throw "Aplicador transacional de atualização falhou. $($_.Exception.Message)"
    }
}

if (-not $NonPortable) {
    if (-not (Test-Path -LiteralPath $PortableMarker)) {
        New-Item -ItemType File -Path $PortableMarker -Force | Out-Null
    }
    $env:CINEPULSE_PORTABLE = '1'
    $env:CINEPULSE_INSTALL_MODE = 'portable'
} else {
    if (Test-Path -LiteralPath $PortableMarker) { Remove-Item -LiteralPath $PortableMarker -Force }
    $env:CINEPULSE_PORTABLE = '0'
    $env:CINEPULSE_INSTALL_MODE = 'installed-self-contained'
}

Apply-PendingUpdate
if ($ApplyUpdateOnly) { exit 0 }

function Install-DesktopShortcut {
    if ($NonPortable) { return }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'cinepulse-files.json'))) { return }
    $Desktop = [Environment]::GetFolderPath('DesktopDirectory')
    if (-not $Desktop) { return }
    $ShortcutPath = Join-Path $Desktop 'CinePulse.lnk'
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = Join-Path $ProjectRoot 'CinePulse.cmd'
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.Description = 'CinePulse - estúdio local de vídeo e visuais musicais'
    $Shortcut.Save()
    Write-Host "Atalho criado: $ShortcutPath"
}

function Set-DedicatedGpuPreference {
    $Nvidia = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
    if (-not $Nvidia) {
        Write-Host 'GPU NVIDIA não detectada; o CinePulse continua disponível em CPU/Vulkan compatível.'
        return
    }
    # Do not write Windows-wide GPU preference registry entries.  Keep the
    # project isolated and express CUDA selection only in this process tree.
    $env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'
    $env:CUDA_VISIBLE_DEVICES = '0'
    $env:CINEPULSE_PREFER_DEDICATED_GPU = '1'
    Write-Host 'CINEPULSE_DEDICATED_GPU_PREFERRED NVIDIA=OK scope=process-only'
}

function Get-PortableUv {
    $BootstrapRoot = Join-Path $RuntimeRoot 'bootstrap'
    $UvExe = Join-Path $BootstrapRoot 'uv.exe'
    $StateFile = Join-Path $BootstrapRoot 'uv-state.json'
    $ExpectedVersion = [string]$BootstrapManifest.uv.version
    $ExpectedSha256 = ([string]$BootstrapManifest.uv.sha256).ToLowerInvariant()
    if ((Test-Path -LiteralPath $UvExe) -and (Test-Path -LiteralPath $StateFile)) {
        try {
            $State = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
            if ($State.schema -eq 1 -and
                [string]$State.version -eq $ExpectedVersion -and
                ([string]$State.sha256).ToLowerInvariant() -eq $ExpectedSha256) {
                return $UvExe
            }
        } catch { }
    }
    if (Test-Path -LiteralPath $BootstrapRoot) { Remove-Item -LiteralPath $BootstrapRoot -Recurse -Force }
    New-Item -ItemType Directory -Path $BootstrapRoot -Force | Out-Null
    $Archive = Join-Path $BootstrapRoot 'uv.zip.part'
    Write-Host "Baixando inicializador portátil uv $ExpectedVersion..."
    Invoke-WebRequest -UseBasicParsing -Uri $BootstrapManifest.uv.url -OutFile $Archive
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    if ($ActualHash -ne $ExpectedSha256) {
        Remove-Item -LiteralPath $Archive -Force
        throw 'O download do inicializador portátil não passou na verificação SHA-256.'
    }
    $Extracted = Join-Path $BootstrapRoot 'extracted'
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
    $Found = Get-ChildItem -LiteralPath $Extracted -Recurse -File -Filter 'uv.exe' | Select-Object -First 1
    if (-not $Found) { throw 'O pacote do uv não contém o executável esperado.' }
    Move-Item -LiteralPath $Found.FullName -Destination $UvExe -Force
    $StateTemp = "$StateFile.part"
    @{ schema = 1; version = $ExpectedVersion; sha256 = $ExpectedSha256 } |
        ConvertTo-Json | Set-Content -LiteralPath $StateTemp -Encoding UTF8
    Move-Item -LiteralPath $StateTemp -Destination $StateFile -Force
    Remove-Item -LiteralPath $Archive -Force
    Remove-Item -LiteralPath $Extracted -Recurse -Force
    return $UvExe
}

function Install-PortableFfmpeg {
    $Destination = Join-Path $ComponentsRoot 'ffmpeg'
    Install-VerifiedArchive -Key 'ffmpeg' -Name "FFmpeg portátil $($BootstrapManifest.ffmpeg.version)" `
        -Manifest $BootstrapManifest.ffmpeg -Destination $Destination `
        -RequiredFiles @('bin\ffmpeg.exe', 'bin\ffprobe.exe') -UseSingleRoot
}

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$Sha256,
        [Parameter(Mandatory)][string]$Destination
    )
    $Expected = $Sha256.ToLowerInvariant()
    if (Test-Path -LiteralPath $Destination) {
        $Existing = (Get-FileHash -Algorithm SHA256 -LiteralPath $Destination).Hash.ToLowerInvariant()
        if ($Existing -eq $Expected) { return }
        Remove-Item -LiteralPath $Destination -Force
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    $Partial = "$Destination.part"
    if (Test-Path -LiteralPath $Partial) { Remove-Item -LiteralPath $Partial -Force }
    Write-Host "Baixando $Name..."
    Add-Type -AssemblyName System.Net.Http
    $Client = [Net.Http.HttpClient]::new()
    $Response = $null
    $Input = $null
    $Output = $null
    try {
        $Response = $Client.GetAsync($Url, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        [void]$Response.EnsureSuccessStatusCode()
        $Total = $Response.Content.Headers.ContentLength
        $Input = $Response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $Output = [IO.File]::Open($Partial, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $Buffer = New-Object byte[] (1024 * 1024)
        [long]$Received = 0
        while (($Read = $Input.Read($Buffer, 0, $Buffer.Length)) -gt 0) {
            $Output.Write($Buffer, 0, $Read)
            $Received += $Read
            $Megabytes = $Received / 1MB
            if ($Total -and $Total -gt 0) {
                $Percent = [Math]::Min(100, [Math]::Floor($Received * 100 / $Total))
                Write-Progress -Activity "Baixando $Name" -Status ("{0:N1} de {1:N1} MB" -f $Megabytes, ($Total / 1MB)) -PercentComplete $Percent
            } else {
                Write-Progress -Activity "Baixando $Name" -Status ("{0:N1} MB" -f $Megabytes)
            }
        }
        Write-Progress -Activity "Baixando $Name" -Completed
    } finally {
        if ($Output) { $Output.Dispose() }
        if ($Input) { $Input.Dispose() }
        if ($Response) { $Response.Dispose() }
        $Client.Dispose()
    }
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Partial).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) {
        Remove-Item -LiteralPath $Partial -Force
        throw "$Name não passou na verificação SHA-256. Nada foi instalado."
    }
    Move-Item -LiteralPath $Partial -Destination $Destination -Force
}

function Install-VerifiedArchive {
    param(
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][object]$Manifest,
        [Parameter(Mandatory)][string]$Destination,
        [Parameter(Mandatory)][string[]]$RequiredFiles,
        [switch]$UseSingleRoot
    )
    $Marker = Join-Path $Destination '.cinepulse-component.json'
    if (Test-Path -LiteralPath $Marker) {
        try {
            $State = Get-Content -LiteralPath $Marker -Raw | ConvertFrom-Json
            $Complete = $true
            foreach ($RequiredFile in $RequiredFiles) {
                if (-not (Test-Path -LiteralPath (Join-Path $Destination $RequiredFile))) { $Complete = $false }
            }
            $StateHash = ([string]$State.sha256).ToLowerInvariant()
            $ManifestHash = ([string]$Manifest.sha256).ToLowerInvariant()
            if ($State.version -eq $Manifest.version -and $StateHash -eq $ManifestHash -and $Complete) { return }
        } catch { }
    }
    $StagingRoot = Join-Path $ComponentsRoot ".staging\$Key"
    $Archive = Join-Path $StagingRoot "$Key.zip"
    $Extracted = Join-Path $StagingRoot 'extracted'
    if (Test-Path -LiteralPath $StagingRoot) { Remove-Item -LiteralPath $StagingRoot -Recurse -Force }
    New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null
    Get-VerifiedDownload -Name $Name -Url $Manifest.url -Sha256 $Manifest.sha256 -Destination $Archive
    Write-Host "Instalando $Name..."
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
    $Incoming = $Extracted
    if ($UseSingleRoot) {
        $Roots = @(Get-ChildItem -LiteralPath $Extracted -Directory)
        if ($Roots.Count -ne 1) { throw "O pacote de $Name não possui a estrutura esperada." }
        $Incoming = $Roots[0].FullName
    }
    foreach ($RequiredFile in $RequiredFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $Incoming $RequiredFile))) { throw "O pacote de $Name está incompleto: $RequiredFile" }
    }
    $Previous = "$Destination.previous"
    if (Test-Path -LiteralPath $Previous) { Remove-Item -LiteralPath $Previous -Recurse -Force }
    if (Test-Path -LiteralPath $Destination) { Move-Item -LiteralPath $Destination -Destination $Previous }
    try {
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        Move-Item -LiteralPath $Incoming -Destination $Destination
        if ($env:CINEPULSE_CI_COMPONENT_FAIL_AFTER_PROMOTE -eq $Key) { throw "Falha injetada após promoção de $Key." }
        @{ schema = 2; key = $Key; version = $Manifest.version; sha256 = $Manifest.sha256 } |
            ConvertTo-Json | Set-Content -LiteralPath $Marker -Encoding UTF8
    } catch {
        if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
        if (Test-Path -LiteralPath $Previous) { Move-Item -LiteralPath $Previous -Destination $Destination }
        throw
    }
    if (Test-Path -LiteralPath $Previous) { Remove-Item -LiteralPath $Previous -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $StagingRoot) { Remove-Item -LiteralPath $StagingRoot -Recurse -Force -ErrorAction SilentlyContinue }
}

function Install-Demucs {
    $AiRoot = Join-Path $ComponentsRoot 'ai'
    $AiVenv = Join-Path $AiRoot 'venv'
    $AiPython = Join-Path $AiVenv 'Scripts\python.exe'
    $ModelRepo = Join-Path $AiRoot 'models\demucs\local_repo'
    $DemucsState = Join-Path $AiRoot 'demucs-install-state.json'
    $Ready = $false
    if ((Test-Path -LiteralPath $AiPython) -and (Test-Path -LiteralPath $DemucsState)) {
        try {
            $State = Get-Content -LiteralPath $DemucsState -Raw | ConvertFrom-Json
            $StateMatches = (
                $State.demucs -eq $BootstrapManifest.demucs.version -and
                $State.torch -eq $BootstrapManifest.demucs.torch_version -and
                $State.soundfile -eq $BootstrapManifest.demucs.soundfile_version -and
                $State.python -eq $BootstrapManifest.python.version -and
                $State.cuda_runtime -eq $BootstrapManifest.demucs.cuda_runtime -and
                $State.torch_index -eq $BootstrapManifest.demucs.torch_index
            )
            if ($StateMatches) {
                $Py = [string]$BootstrapManifest.python.version
                $Torch = [string]$BootstrapManifest.demucs.torch_version
                $Demucs = [string]$BootstrapManifest.demucs.version
                $SoundFile = [string]$BootstrapManifest.demucs.soundfile_version
                & $AiPython -c "import importlib.metadata as m, platform, torch; ok=(platform.python_version() == '$Py' and torch.__version__ == '$Torch' and m.version('demucs') == '$Demucs' and m.version('soundfile') == '$SoundFile'); raise SystemExit(0 if ok else 1)" *> $null
                $Ready = $LASTEXITCODE -eq 0
            }
        } catch { $Ready = $false }
    }
    if (-not $Ready) {
        Write-Host "Preparando ambiente de IA para Demucs $($BootstrapManifest.demucs.version)..."
        if (Test-Path -LiteralPath $AiVenv) { Remove-Item -LiteralPath $AiVenv -Recurse -Force }
        & $PythonExe -m venv $AiVenv
        if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente privado do Demucs.' }
        if (-not $UvExe) { $script:UvExe = Get-PortableUv }
        $NeuralLock = Join-Path $ProjectRoot 'requirements-neural.lock'
        if (-not (Test-Path -LiteralPath $NeuralLock)) { throw 'Lock neural ausente; recusando instalar dependências não reproduzíveis.' }
        $TorchIndex = [string]$BootstrapManifest.demucs.torch_index
        if (-not $TorchIndex.StartsWith('https://download.pytorch.org/whl/', [StringComparison]::OrdinalIgnoreCase)) { throw 'Índice oficial do PyTorch ausente ou inválido no manifesto de bootstrap.' }
        Write-Host "Resolvendo PyTorch $($BootstrapManifest.demucs.torch_version) pelo índice oficial CUDA: $TorchIndex"
        & $UvExe pip install --python $AiPython --require-hashes --index $TorchIndex -r $NeuralLock
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o runtime neural hash-locked do Demucs.' }
    }
    New-Item -ItemType Directory -Path $ModelRepo -Force | Out-Null
    foreach ($Weight in $BootstrapManifest.demucs.weights) {
        Get-VerifiedDownload -Name "modelo Demucs $($Weight.file)" -Url $Weight.url -Sha256 $Weight.sha256 -Destination (Join-Path $ModelRepo $Weight.file)
    }
    @"
models: ['f7e0c4bc', 'd12395a8', '92cfc3b6', '04573f0d']
weights:
  [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]
"@ | Set-Content -LiteralPath (Join-Path $ModelRepo 'htdemucs_ft.yaml') -Encoding UTF8
    @{
        schema = 2
        python = $BootstrapManifest.python.version
        demucs = $BootstrapManifest.demucs.version
        torch = $BootstrapManifest.demucs.torch_version
        soundfile = $BootstrapManifest.demucs.soundfile_version
        cuda_runtime = $BootstrapManifest.demucs.cuda_runtime
        torch_index = $BootstrapManifest.demucs.torch_index
    } | ConvertTo-Json | Set-Content -LiteralPath $DemucsState -Encoding UTF8
}

function Install-CompleteComponents {
    param([string[]]$Selected = @('real-esrgan', 'rife', 'demucs'))
    $RealDestination = Join-Path $ComponentsRoot 'real-esrgan'
    $RifeDestination = Join-Path $ComponentsRoot 'ai\models\rife\portable\rife-ncnn-vulkan-20221029-windows'
    if ('real-esrgan' -in $Selected) {
        Install-VerifiedArchive -Key 'real-esrgan' -Name 'Real-ESRGAN' `
            -Manifest $BootstrapManifest.real_esrgan -Destination $RealDestination `
            -RequiredFiles @('realesrgan-ncnn-vulkan.exe', 'models\realesr-animevideov3-x2.bin', 'models\realesr-animevideov3-x2.param')
        if (-not (Test-Path -LiteralPath (Join-Path $RealDestination 'realesrgan-ncnn-vulkan.exe'))) {
            throw 'A instalação do Real-ESRGAN ficou incompleta.'
        }
    }
    if ('rife' -in $Selected) {
        Install-VerifiedArchive -Key 'rife' -Name 'RIFE' `
            -Manifest $BootstrapManifest.rife -Destination $RifeDestination `
            -RequiredFiles @('rife-ncnn-vulkan.exe', 'rife-v4.6\flownet.bin', 'rife-v4.6\flownet.param') -UseSingleRoot
        if (-not (Test-Path -LiteralPath (Join-Path $RifeDestination 'rife-ncnn-vulkan.exe'))) {
            throw 'A instalação do RIFE ficou incompleta.'
        }
    }
    if ('demucs' -in $Selected) { Install-Demucs }
    Write-Host "CINEPULSE_COMPONENTS_READY selected=$($Selected -join ',')"
}

$ExpectedPythonVersion = [string]$BootstrapManifest.python.version
$RuntimeRebuilt = $false
$RebuildRuntime = $Repair -or -not (Test-Path -LiteralPath $PythonExe)
if (-not $RebuildRuntime) {
    try {
        $ActualPythonVersion = (& $PythonExe -c "import platform; print(platform.python_version())").Trim()
        if ($LASTEXITCODE -ne 0 -or $ActualPythonVersion -ne $ExpectedPythonVersion.Trim()) {
            Write-Host "Runtime Python mudou: instalado=$ActualPythonVersion esperado=$ExpectedPythonVersion. Recriando ambiente privado..."
            $RebuildRuntime = $true
        }
    } catch {
        Write-Host 'Runtime Python existente está inválido. Recriando ambiente privado...'
        $RebuildRuntime = $true
    }
}

if ($InstallOnly) { Write-Host '[1/4] Preparando o ambiente Python privado...' }
if ($RebuildRuntime) {
    if (Test-Path -LiteralPath $VenvRoot) {
        $ResolvedRuntime = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\') + '\'
        $ResolvedVenv = [IO.Path]::GetFullPath($VenvRoot)
        if (-not $ResolvedVenv.StartsWith($ResolvedRuntime, [StringComparison]::OrdinalIgnoreCase)) { throw 'A pasta do ambiente não pertence ao CinePulse.' }
        Remove-Item -LiteralPath $VenvRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    if (-not $UvExe) { $UvExe = Get-PortableUv }
    Write-Host "Preparando Python gerenciado $ExpectedPythonVersion dentro de $RuntimeRoot..."
    & $UvExe venv --python $ExpectedPythonVersion --python-preference only-managed $VenvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar o Python gerenciado do CinePulse.' }
    $RuntimeRebuilt = $true
}
if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'Runtime Python privado não foi criado.' }
$ActualPythonVersion = (& $PythonExe -c "import platform; print(platform.python_version())").Trim()
if ($LASTEXITCODE -ne 0 -or $ActualPythonVersion -ne $ExpectedPythonVersion.Trim()) {
    throw "Runtime Python inesperado após reconstrução. Esperado $ExpectedPythonVersion, obtido $ActualPythonVersion."
}

$ProjectHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'pyproject.toml')).Hash
$LockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'requirements.lock')).Hash
$ExpectedState = "$ExpectedPythonVersion`n$ProjectHash`n$LockHash"
$CurrentState = if (Test-Path -LiteralPath $InstallState) { Get-Content -LiteralPath $InstallState -Raw } else { '' }
$RuntimePackagesHealthy = $false
if (-not $RuntimeRebuilt) {
    try {
        & $PythonExe -c "import numpy, cinepulse; raise SystemExit(0)" *> $null
        $RuntimePackagesHealthy = $LASTEXITCODE -eq 0
    } catch {
        $RuntimePackagesHealthy = $false
    }
}
if ($InstallOnly) { Write-Host '[2/4] Verificando dependências do CinePulse...' }
if ($Repair -or $RuntimeRebuilt -or -not $RuntimePackagesHealthy -or $CurrentState.Trim() -ne $ExpectedState.Trim()) {
    & $PythonExe -m pip --version *> $null
    if ($LASTEXITCODE -eq 0) {
        & $PythonExe -m pip install --disable-pip-version-check --quiet --require-hashes --only-binary=:all: --requirement (Join-Path $ProjectRoot 'requirements.lock')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências do CinePulse.' }
        & $PythonExe -m pip install --disable-pip-version-check --quiet --no-deps --editable $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o CinePulse no ambiente privado.' }
    } else {
        if (-not $UvExe) { $UvExe = Get-PortableUv }
        & $UvExe pip install --python $PythonExe --quiet --require-hashes --only-binary=:all: --requirement (Join-Path $ProjectRoot 'requirements.lock')
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências com uv.' }
        & $UvExe pip install --python $PythonExe --quiet --no-deps --editable $ProjectRoot
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o CinePulse com uv.' }
    }
    Set-Content -LiteralPath $InstallState -Value $ExpectedState -Encoding UTF8
}

# A build portátil fixada garante os mesmos codecs, HDR e libvmaf em qualquer computador.
if ($InstallOnly) { Write-Host '[3/4] Verificando FFmpeg, codecs, HDR e VMAF...' }
$InstallAll = $RequestedComponents.Count -eq 0
if ($InstallAll -or 'ffmpeg' -in $RequestedComponents) { Install-PortableFfmpeg }

if (-not $CoreOnly) {
    $AiComponents = if ($InstallAll) { @('real-esrgan', 'rife', 'demucs') } else {
        @($RequestedComponents | Where-Object { $_ -in @('real-esrgan', 'rife', 'demucs') })
    }
    if ($AiComponents.Count) {
        if ($InstallOnly) { Write-Host "[4/4] Verificando componentes de IA: $($AiComponents -join ', ')..." }
        Install-CompleteComponents -Selected $AiComponents
    }
}
$LocalBin = @(
    (Join-Path $VenvRoot 'Scripts'),
    (Join-Path $ComponentsRoot 'ffmpeg\bin')
) -join ';'
$env:PATH = "$LocalBin;$env:PATH"
Set-DedicatedGpuPreference
if ($InstallOnly) {
    Install-DesktopShortcut
    Write-Host 'CINEPULSE_INSTALL_COMPLETE status=OK'
    if ($TranscriptStarted) { Stop-Transcript | Out-Null }
    exit 0
}

if ($Diagnostics) {
    & $PythonExe -m cinepulse.diagnostics
    exit $LASTEXITCODE
}

& $PythonExe -m cinepulse
exit $LASTEXITCODE
