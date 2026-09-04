from pathlib import Path

path = Path('installer/Start-CinePulse.ps1')
text = path.read_text(encoding='utf-8-sig')


def once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, got {count}')
    text = text.replace(old, new, 1)


once(
    """$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$PortableMarker = Join-Path $ProjectRoot '.cinepulse-portable'
$UserDataRoot = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'CinePulse' } else { Join-Path $HOME 'AppData\\Local\\CinePulse' }
$RuntimeRoot = if ($NonPortable) { Join-Path $UserDataRoot 'runtime' } else { Join-Path $ProjectRoot '.runtime' }
$ComponentsRoot = if ($NonPortable) { Join-Path $UserDataRoot 'components' } else { Join-Path $ProjectRoot 'components' }
$VenvRoot = Join-Path $RuntimeRoot 'python'
$PythonExe = Join-Path $VenvRoot 'Scripts\\python.exe'
$InstallState = Join-Path $RuntimeRoot 'install-state.txt'
$BootstrapManifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'bootstrap-manifest.json') -Raw | ConvertFrom-Json
$UvExe = $null
$TranscriptStarted = $false
""",
    """$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
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
$PythonExe = Join-Path $VenvRoot 'Scripts\\python.exe'
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
""",
    'self-contained roots',
)

once(
    """    $InstallerLog = if ($NonPortable) { Join-Path $UserDataRoot 'logs\\installer.log' } else { Join-Path $ProjectRoot 'data\\logs\\installer.log' }
""",
    """    $InstallerLog = Join-Path $DataRoot 'logs\\installer.log'
""",
    'installer log root',
)

once(
    """if (-not $NonPortable) {
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
""",
    """if (-not $NonPortable) {
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
""",
    'mode environment',
)

once(
    """function Set-DedicatedGpuPreference {
    $Nvidia = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
    if (-not $Nvidia) {
        Write-Host 'GPU dedicada NVIDIA não detectada; seleção automática do Windows mantida.'
        return
    }
    $env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'
    $env:CUDA_VISIBLE_DEVICES = '0'
    $env:CINEPULSE_PREFER_DEDICATED_GPU = '1'
    try {
        $PreferenceKey = 'HKCU:\\Software\\Microsoft\\DirectX\\UserGpuPreferences'
        New-Item -Path $PreferenceKey -Force | Out-Null
        $Executables = @(
            $PythonExe,
            (Join-Path $VenvRoot 'Scripts\\pythonw.exe'),
            (Join-Path $ComponentsRoot 'ffmpeg\\bin\\ffmpeg.exe'),
            (Join-Path $ComponentsRoot 'real-esrgan\\realesrgan-ncnn-vulkan.exe'),
            (Join-Path $ComponentsRoot 'ai\\models\\rife\\portable\\rife-ncnn-vulkan-20221029-windows\\rife-ncnn-vulkan.exe')
        )
        $Configured = 0
        foreach ($Executable in $Executables) {
            if (Test-Path -LiteralPath $Executable) {
                $Resolved = [IO.Path]::GetFullPath($Executable)
                New-ItemProperty -Path $PreferenceKey -Name $Resolved -PropertyType String -Value 'GpuPreference=2;' -Force | Out-Null
                $Configured++
            }
        }
        Write-Host \"CINEPULSE_DEDICATED_GPU_PREFERRED NVIDIA=OK executables=$Configured\"
    } catch {
        Write-Warning \"O Windows não aceitou a preferência gráfica; CUDA e seleção automática continuam ativas. $($_.Exception.Message)\"
    }
}
""",
    """function Set-DedicatedGpuPreference {
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
""",
    'gpu preference isolation',
)

once(
    """    $env:UV_PYTHON_INSTALL_DIR = Join-Path $RuntimeRoot 'pythons'
    Write-Host \"Preparando Python gerenciado $($BootstrapManifest.python.version) para modo $($env:CINEPULSE_INSTALL_MODE)...\"
""",
    """    Write-Host \"Preparando Python gerenciado $($BootstrapManifest.python.version) dentro de $RuntimeRoot...\"
""",
    'managed python directory',
)

# Make local tools win PATH resolution after they exist, while keeping Windows
# system tools (PowerShell, nvidia-smi, shell APIs) available.
needle = """Set-DedicatedGpuPreference
if ($InstallOnly) {
"""
replacement = """$LocalBin = @(
    (Join-Path $VenvRoot 'Scripts'),
    (Join-Path $ComponentsRoot 'ffmpeg\\bin')
) -join ';'
$env:PATH = "$LocalBin;$env:PATH"
Set-DedicatedGpuPreference
if ($InstallOnly) {
"""
once(needle, replacement, 'local PATH precedence')

path.write_text(text, encoding='utf-8-sig')
print('CINEPULSE_INSTALLER_V2_SELF_CONTAINED_PATCH_OK')
