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
$UserDataRoot = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'CinePulse' } else { Join-Path $HOME 'AppData\Local\CinePulse' }
$RuntimeRoot = if ($NonPortable) { Join-Path $UserDataRoot 'runtime' } else { Join-Path $ProjectRoot '.runtime' }
$ComponentsRoot = if ($NonPortable) { Join-Path $UserDataRoot 'components' } else { Join-Path $ProjectRoot 'components' }
$VenvRoot = Join-Path $RuntimeRoot 'python'
$PythonExe = Join-Path $VenvRoot 'Scripts\python.exe'
$InstallState = Join-Path $RuntimeRoot 'install-state.txt'
$BootstrapManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bootstrap-manifest.json') -Raw | ConvertFrom-Json
$UvExe = $null
$TranscriptStarted = $false
$RequestedComponents = @($ComponentsCsv.Split(',', [StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { $_.Trim().ToLowerInvariant() })
$AllowedComponents = @('ffmpeg', 'real-esrgan', 'rife', 'demucs')
foreach ($Requested in $RequestedComponents) {
    if ($Requested -notin $AllowedComponents) { throw "Componente desconhecido: $Requested" }
}

if ($InstallOnly) {
    try { $Host.UI.RawUI.WindowTitle = 'CinePulse - Instalando componentes locais' } catch { }
    $InstallerLog = if ($NonPortable) { Join-Path $UserDataRoot 'logs\installer.log' } else { Join-Path $ProjectRoot 'data\logs\installer.log' }
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
        'CinePulse.cmd', 'Install-CinePulse.cmd', 'cinepulse-files.json', 'LICENSE', 'README.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md',
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
    $env:CINEPULSE_INSTALL_MODE = 'portable'
} else {
    if (Test-Path -LiteralPath $PortableMarker) { Remove-Item -LiteralPath $PortableMarker -Force }
    $env:CINEPULSE_PORTABLE = '0'
    $env:CINEPULSE_INSTALL_MODE = 'installed'
}
$env:CINEPULSE_COMPONENTS_DIR = $ComponentsRoot
if ($NonPortable) { $env:CINEPULSE_DATA_DIR = $UserDataRoot }

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
        Write-Host 'GPU dedicada NVIDIA não detectada; seleção automática do Windows mantida.'
        return
    }
    $env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'
    $env:CUDA_VISIBLE_DEVICES = '0'
    $env:CINEPULSE_PREFER_DEDICATED_GPU = '1'
    try {
        $PreferenceKey = 'HKCU:\Software\Microsoft\DirectX\UserGpuPreferences'
        New-Item -Path $PreferenceKey -Force | Out-Null
        $Executables = @(
            $PythonExe,
            (Join-Path $VenvRoot 'Scripts\pythonw.exe'),
            (Join-Path $ComponentsRoot 'ffmpeg\bin\ffmpeg.exe'),
            (Join-Path $ComponentsRoot 'real-esrgan\realesrgan-ncnn-vulkan.exe'),
            (Join-Path $ComponentsRoot 'ai\models\rife\portable\rife-ncnn-vulkan-20221029-windows\rife-ncnn-vulkan.exe')
        )
        $Configured = 0
        foreach ($Executable in $Executables) {
            if (Test-Path -LiteralPath $Executable) {
                $Resolved = [IO.Path]::GetFullPath($Executable)
                New-ItemProperty -Path $PreferenceKey -Name $Resolved -PropertyType String -Value 'GpuPreference=2;' -Force | Out-Null
                $Configured++
            }
        }
        Write-Host "CINEPULSE_DEDICATED_GPU_PREFERRED NVIDIA=OK executables=$Configured"
    } catch {
        Write-Warning "O Windows não aceitou a preferência gráfica; CUDA e seleção automática continuam ativas. $($_.Exception.Message)"
    }
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
    $Destination = Join-Path $ComponentsRoot 'ffmpeg'
    $FfmpegExe = Join-Path $Destination 'bin\ffmpeg.exe'
    $FfprobeExe = Join-Path $Destination 'bin\ffprobe.exe'
    if ((Test-Path -LiteralPath $FfmpegExe) -and (Test-Path -LiteralPath $FfprobeExe)) { return }
    $StagingRoot = Join-Path $ComponentsRoot '.staging\ffmpeg'
    $Archive = Join-Path $StagingRoot 'ffmpeg.zip.part'
    $Extracted = Join-Path $StagingRoot 'extracted'
    New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null
    Get-VerifiedDownload -Name "FFmpeg portátil $($BootstrapManifest.ffmpeg.version)" `
        -Url $BootstrapManifest.ffmpeg.url -Sha256 $BootstrapManifest.ffmpeg.sha256 -Destination $Archive
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
            if ($State.version -eq $Manifest.version -and $Complete) { return }
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
    $Previous = "$Destination.previous"
    if (Test-Path -LiteralPath $Previous) { Remove-Item -LiteralPath $Previous -Recurse -Force }
    if (Test-Path -LiteralPath $Destination) { Move-Item -LiteralPath $Destination -Destination $Previous }
    try {
        New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
        Move-Item -LiteralPath $Incoming -Destination $Destination
        @{ schema = 1; key = $Key; version = $Manifest.version; sha256 = $Manifest.sha256 } |
            ConvertTo-Json | Set-Content -LiteralPath $Marker -Encoding UTF8
    } catch {
        if ((Test-Path -LiteralPath $Previous) -and -not (Test-Path -LiteralPath $Destination)) {
            Move-Item -LiteralPath $Previous -Destination $Destination
        }
        throw
    }
    if (Test-Path -LiteralPath $Previous) { Remove-Item -LiteralPath $Previous -Recurse -Force }
    if (Test-Path -LiteralPath $StagingRoot) { Remove-Item -LiteralPath $StagingRoot -Recurse -Force }
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
            if ($State.demucs -eq $BootstrapManifest.demucs.version -and $State.torch -eq $BootstrapManifest.demucs.torch_version) {
                & $AiPython -c "import demucs, torch; raise SystemExit(0 if torch.__version__ else 1)" *> $null
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
        & $UvExe pip install --python $AiPython --index-url $BootstrapManifest.demucs.torch_index `
            "torch==$($BootstrapManifest.demucs.torch_version)" `
            "torchaudio==$($BootstrapManifest.demucs.torchaudio_version)"
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar a aceleração PyTorch do Demucs.' }
        & $UvExe pip install --python $AiPython --index-url 'https://pypi.org/simple' `
            "demucs==$($BootstrapManifest.demucs.version)" soundfile
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o Demucs.' }
    }
    New-Item -ItemType Directory -Path $ModelRepo -Force | Out-Null
    foreach ($Weight in $BootstrapManifest.demucs.weights) {
        Get-VerifiedDownload -Name "modelo Demucs $($Weight.file)" -Url $Weight.url -Sha256 $Weight.sha256 `
            -Destination (Join-Path $ModelRepo $Weight.file)
    }
    @"
models: ['f7e0c4bc', 'd12395a8', '92cfc3b6', '04573f0d']
weights:
  [[1., 0., 0., 0.], [0., 1., 0., 0.], [0., 0., 1., 0.], [0., 0., 0., 1.]]
"@ | Set-Content -LiteralPath (Join-Path $ModelRepo 'htdemucs_ft.yaml') -Encoding UTF8
    @{ schema = 1; demucs = $BootstrapManifest.demucs.version; torch = $BootstrapManifest.demucs.torch_version } |
        ConvertTo-Json | Set-Content -LiteralPath $DemucsState -Encoding UTF8
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

if ($Repair -and (Test-Path -LiteralPath $VenvRoot)) {
    $ResolvedRuntime = (Resolve-Path -LiteralPath $RuntimeRoot).Path
    $ResolvedVenv = (Resolve-Path -LiteralPath $VenvRoot).Path
    if (-not $ResolvedVenv.StartsWith($ResolvedRuntime, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'A pasta do ambiente não pertence ao CinePulse.'
    }
    Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}

if ($InstallOnly) { Write-Host '[1/4] Preparando o ambiente Python privado...' }
if (-not (Test-Path -LiteralPath $PythonExe)) {
    New-Item -ItemType Directory -Path $RuntimeRoot -Force | Out-Null
    $UvExe = Get-PortableUv
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeRoot 'pythons'
    Write-Host "Preparando Python gerenciado $($BootstrapManifest.python.version) para modo $($env:CINEPULSE_INSTALL_MODE)..."
    & $UvExe venv --python $BootstrapManifest.python.version --python-preference only-managed $VenvRoot
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar o Python gerenciado do CinePulse.' }
}

$ExpectedPythonVersion = [string]$BootstrapManifest.python.version
$ActualPythonVersion = & $PythonExe -c "import platform; print(platform.python_version())"
if ($ActualPythonVersion.Trim() -ne $ExpectedPythonVersion.Trim()) {
    throw "Runtime Python inesperado. Esperado $ExpectedPythonVersion, obtido $($ActualPythonVersion.Trim())."
}

$ProjectHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'pyproject.toml')).Hash
$LockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'requirements.lock')).Hash
$ExpectedState = "$ProjectHash`n$LockHash"
$CurrentState = if (Test-Path -LiteralPath $InstallState) { Get-Content -LiteralPath $InstallState -Raw } else { '' }
if ($InstallOnly) { Write-Host '[2/4] Verificando dependências do CinePulse...' }
if ($Repair -or $CurrentState.Trim() -ne $ExpectedState.Trim()) {
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
