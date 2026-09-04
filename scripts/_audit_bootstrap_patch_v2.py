from pathlib import Path
import re

path = Path('installer/Start-CinePulse.ps1')
text = path.read_text(encoding='utf-8-sig')


def replace_block(start: str, next_start: str, replacement: str, label: str) -> None:
    global text
    pattern = re.compile(re.escape(start) + r'.*?(?=' + re.escape(next_start) + r')', re.S)
    value = replacement.rstrip() + '\n\n'
    text, count = pattern.subn(lambda _m: value, text, count=1)
    if count != 1:
        raise SystemExit(f'{label}: expected one block, got {count}')


replace_block(
    'function Apply-PendingUpdate {', 'if (-not $NonPortable) {',
    r'''function Apply-PendingUpdate {
    $Applier = Join-Path $PSScriptRoot 'Apply-CinePulseUpdate.ps1'
    if (-not (Test-Path -LiteralPath $Applier)) { throw 'Aplicador transacional de atualização não encontrado.' }
    & $Applier -ProjectRoot $ProjectRoot -RuntimeRoot $RuntimeRoot
    if ($LASTEXITCODE -ne 0) { throw "Aplicador transacional de atualização falhou com código $LASTEXITCODE." }
}''', 'transactional updater delegation')

replace_block(
    'function Get-PortableUv {', 'function Install-PortableFfmpeg {',
    r'''function Get-PortableUv {
    $BootstrapRoot = Join-Path $RuntimeRoot 'bootstrap'
    $UvExe = Join-Path $BootstrapRoot 'uv.exe'
    $VersionFile = Join-Path $BootstrapRoot 'uv-version.txt'
    $ExpectedVersion = [string]$BootstrapManifest.uv.version
    if ((Test-Path -LiteralPath $UvExe) -and (Test-Path -LiteralPath $VersionFile)) {
        $InstalledVersion = (Get-Content -LiteralPath $VersionFile -Raw).Trim()
        if ($InstalledVersion -eq $ExpectedVersion) { return $UvExe }
    }
    if (Test-Path -LiteralPath $BootstrapRoot) { Remove-Item -LiteralPath $BootstrapRoot -Recurse -Force }
    New-Item -ItemType Directory -Path $BootstrapRoot -Force | Out-Null
    $Archive = Join-Path $BootstrapRoot 'uv.zip.part'
    Write-Host "Baixando inicializador portátil uv $ExpectedVersion..."
    Invoke-WebRequest -UseBasicParsing -Uri $BootstrapManifest.uv.url -OutFile $Archive
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Archive).Hash.ToLowerInvariant()
    if ($ActualHash -ne $BootstrapManifest.uv.sha256.ToLowerInvariant()) {
        Remove-Item -LiteralPath $Archive -Force
        throw 'O download do inicializador portátil não passou na verificação SHA-256.'
    }
    $Extracted = Join-Path $BootstrapRoot 'extracted'
    Expand-Archive -LiteralPath $Archive -DestinationPath $Extracted -Force
    $Found = Get-ChildItem -LiteralPath $Extracted -Recurse -File -Filter 'uv.exe' | Select-Object -First 1
    if (-not $Found) { throw 'O pacote do uv não contém o executável esperado.' }
    Move-Item -LiteralPath $Found.FullName -Destination $UvExe -Force
    Set-Content -LiteralPath $VersionFile -Value $ExpectedVersion -Encoding ascii
    Remove-Item -LiteralPath $Archive -Force
    Remove-Item -LiteralPath $Extracted -Recurse -Force
    return $UvExe
}''', 'uv version-aware cache')

replace_block(
    'function Install-PortableFfmpeg {', 'function Get-VerifiedDownload {',
    r'''function Install-PortableFfmpeg {
    $Destination = Join-Path $ComponentsRoot 'ffmpeg'
    Install-VerifiedArchive -Key 'ffmpeg' -Name "FFmpeg portátil $($BootstrapManifest.ffmpeg.version)" `
        -Manifest $BootstrapManifest.ffmpeg -Destination $Destination `
        -RequiredFiles @('bin\ffmpeg.exe', 'bin\ffprobe.exe') -UseSingleRoot
}''', 'ffmpeg version-aware component install')

replace_block(
    'function Install-VerifiedArchive {', 'function Install-Demucs {',
    r'''function Install-VerifiedArchive {
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
}''', 'component promotion transaction')

replace_block(
    'function Install-Demucs {', 'function Install-CompleteComponents {',
    r'''function Install-Demucs {
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
}''', 'demucs runtime identity')

pattern = re.compile(r"if \(\$Repair -and \(Test-Path -LiteralPath \$VenvRoot\)\) \{.*?(?=\$ProjectHash =)", re.S)
replacement = r'''$ExpectedPythonVersion = [string]$BootstrapManifest.python.version
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
}
if (-not (Test-Path -LiteralPath $PythonExe)) { throw 'Runtime Python privado não foi criado.' }
$ActualPythonVersion = (& $PythonExe -c "import platform; print(platform.python_version())").Trim()
if ($LASTEXITCODE -ne 0 -or $ActualPythonVersion -ne $ExpectedPythonVersion.Trim()) {
    throw "Runtime Python inesperado após reconstrução. Esperado $ExpectedPythonVersion, obtido $ActualPythonVersion."
}

'''
value = replacement.rstrip() + '\n\n'
text, count = pattern.subn(lambda _m: value, text, count=1)
if count != 1:
    raise SystemExit(f'python runtime self-heal: expected one block, got {count}')

old = '$ExpectedState = "$ProjectHash`n$LockHash"'
new = '$ExpectedState = "$ExpectedPythonVersion`n$ProjectHash`n$LockHash"'
if old not in text:
    raise SystemExit('install-state pattern missing')
text = text.replace(old, new, 1)

path.write_text(text, encoding='utf-8-sig')
print('CINEPULSE_AUDIT_BOOTSTRAP_HARDENING_OK')
