[CmdletBinding()]
param(
    [string]$SessionRoot = '',
    [int]$MonitorMinutes = 0,
    [int]$SampleSeconds = 15,
    [int]$ProcessId = 0,
    [string]$OutputPath = '',
    [string]$ScratchPath = '',
    [switch]$GenerateOnly,
    [switch]$OpenFolder
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
if (-not $SessionRoot) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $SessionRoot = Join-Path $ProjectRoot ("artifacts\overlay-acceptance\$stamp")
}
$SessionRoot = [System.IO.Path]::GetFullPath($SessionRoot)
New-Item -ItemType Directory -Path $SessionRoot -Force | Out-Null

function Invoke-OptionalText {
    param([scriptblock]$Action)
    try {
        $value = & $Action 2>$null | Out-String
        return $value.Trim()
    } catch {
        return ''
    }
}

function Get-FirstLine {
    param([string]$Command, [string[]]$Arguments = @())
    $resolved = Get-Command $Command -ErrorAction SilentlyContinue
    if (-not $resolved) { return $null }
    try {
        $output = & $resolved.Source @Arguments 2>&1
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { return $null }
        return (($output | Select-Object -First 1) -as [string]).Trim()
    } catch {
        return $null
    }
}

function Get-DirectorySizeBytes {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    try {
        $total = 0L
        foreach ($file in [System.IO.Directory]::EnumerateFiles($Path, '*', [System.IO.SearchOption]::AllDirectories)) {
            try { $total += ([System.IO.FileInfo]$file).Length } catch { }
        }
        return $total
    } catch {
        return $null
    }
}

function Convert-BytesToGb {
    param($Bytes)
    if ($null -eq $Bytes) { return $null }
    return [math]::Round(([double]$Bytes / 1GB), 3)
}

function Get-NvidiaSample {
    $command = Get-Command 'nvidia-smi' -ErrorAction SilentlyContinue
    if (-not $command) { return $null }
    try {
        $line = & $command.Source '--query-gpu=name,driver_version,memory.used,memory.total,utilization.gpu,temperature.gpu' '--format=csv,noheader,nounits' 2>$null | Select-Object -First 1
        if (-not $line) { return $null }
        $parts = @($line -split ',' | ForEach-Object { $_.Trim() })
        if ($parts.Count -lt 6) { return $null }
        return [pscustomobject]@{
            name = $parts[0]
            driver = $parts[1]
            memory_used_mb = [double]$parts[2]
            memory_total_mb = [double]$parts[3]
            utilization_percent = [double]$parts[4]
            temperature_c = [double]$parts[5]
        }
    } catch {
        return $null
    }
}

function Get-ProcessSample {
    param([int]$RequestedPid)
    try {
        if ($RequestedPid -gt 0) {
            $processes = @(Get-Process -Id $RequestedPid -ErrorAction Stop)
        } else {
            $processes = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('cinepulse','python','pythonw') })
        }
        if (-not $processes) { return $null }
        return [pscustomobject]@{
            process_count = $processes.Count
            working_set_mb = [math]::Round((($processes | Measure-Object -Property WorkingSet64 -Sum).Sum / 1MB), 2)
            private_memory_mb = [math]::Round((($processes | Measure-Object -Property PrivateMemorySize64 -Sum).Sum / 1MB), 2)
            cpu_seconds = [math]::Round((($processes | Measure-Object -Property CPU -Sum).Sum), 2)
            ids = @($processes.Id)
        }
    } catch {
        return $null
    }
}

$gitHead = Invoke-OptionalText { git -C $ProjectRoot rev-parse HEAD }
$gitBranch = Invoke-OptionalText { git -C $ProjectRoot branch --show-current }
$gitStatus = Invoke-OptionalText { git -C $ProjectRoot status --short }
$pythonVersion = Get-FirstLine 'python' @('--version')
if (-not $pythonVersion) { $pythonVersion = Get-FirstLine 'py' @('--version') }
$ffmpegVersion = Get-FirstLine 'ffmpeg' @('-version')
$ffprobeVersion = Get-FirstLine 'ffprobe' @('-version')

$osInfo = $null
$cpuInfo = @()
$videoInfo = @()
try { $osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop } catch { }
try { $cpuInfo = @(Get-CimInstance Win32_Processor -ErrorAction Stop) } catch { }
try { $videoInfo = @(Get-CimInstance Win32_VideoController -ErrorAction Stop) } catch { }

$dpi = [ordered]@{ log_pixels = $null; applied_dpi = $null }
try {
    $desktop = Get-ItemProperty 'HKCU:\Control Panel\Desktop' -ErrorAction Stop
    if ($desktop.PSObject.Properties.Name -contains 'LogPixels') { $dpi.log_pixels = $desktop.LogPixels }
} catch { }
try {
    $windowMetrics = Get-ItemProperty 'HKCU:\Control Panel\Desktop\WindowMetrics' -ErrorAction Stop
    if ($windowMetrics.PSObject.Properties.Name -contains 'AppliedDPI') { $dpi.applied_dpi = $windowMetrics.AppliedDPI }
} catch { }

$drives = @()
foreach ($drive in Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue) {
    if (-not $drive.Root) { continue }
    $drives += [pscustomobject]@{
        root = $drive.Root
        used_gb = if ($null -ne $drive.Used) { Convert-BytesToGb $drive.Used } else { $null }
        free_gb = if ($null -ne $drive.Free) { Convert-BytesToGb $drive.Free } else { $null }
    }
}

$nvidia = Get-NvidiaSample
$environment = [ordered]@{
    schema = 'cinepulse.overlay-manual-acceptance/1'
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    computer = $env:COMPUTERNAME
    user = $env:USERNAME
    project_root = $ProjectRoot
    git = [ordered]@{
        branch = $gitBranch
        head = $gitHead
        dirty = [bool]$gitStatus
        status_short = $gitStatus
    }
    runtime = [ordered]@{
        powershell = $PSVersionTable.PSVersion.ToString()
        python = $pythonVersion
        ffmpeg = $ffmpegVersion
        ffprobe = $ffprobeVersion
    }
    windows = if ($osInfo) {
        [ordered]@{
            caption = $osInfo.Caption
            version = $osInfo.Version
            build = $osInfo.BuildNumber
            total_memory_gb = [math]::Round(($osInfo.TotalVisibleMemorySize * 1KB / 1GB), 2)
            free_memory_gb = [math]::Round(($osInfo.FreePhysicalMemory * 1KB / 1GB), 2)
        }
    } else {
        [ordered]@{ caption = [Environment]::OSVersion.VersionString }
    }
    cpu = @($cpuInfo | ForEach-Object {
        [ordered]@{ name=$_.Name; cores=$_.NumberOfCores; logical_processors=$_.NumberOfLogicalProcessors; max_clock_mhz=$_.MaxClockSpeed }
    })
    display_adapters = @($videoInfo | ForEach-Object {
        [ordered]@{
            name=$_.Name
            driver_version=$_.DriverVersion
            current_width=$_.CurrentHorizontalResolution
            current_height=$_.CurrentVerticalResolution
            current_refresh_hz=$_.CurrentRefreshRate
            adapter_ram_gb=if ($_.AdapterRAM) { [math]::Round(([double]$_.AdapterRAM / 1GB), 2) } else { $null }
        }
    })
    dpi_registry = $dpi
    nvidia = $nvidia
    drives = $drives
    requested_monitor = [ordered]@{
        minutes = $MonitorMinutes
        sample_seconds = $SampleSeconds
        process_id = $ProcessId
        output_path = $OutputPath
        scratch_path = $ScratchPath
    }
}

$environmentPath = Join-Path $SessionRoot 'environment.json'
$environment | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $environmentPath -Encoding UTF8

$headShort = if ($gitHead -and $gitHead.Length -ge 12) { $gitHead.Substring(0,12) } else { $gitHead }
$checklistPath = Join-Path $SessionRoot 'ACCEPTANCE.md'
$checklist = @"
# CinePulse Overlay Composer — Manual Acceptance Session

- Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')
- Machine: $env:COMPUTERNAME
- Branch: $gitBranch
- Commit: $headShort
- Evidence folder: `$SessionRoot`

## Session result

- [ ] PASS — suitable for continued Preview rollout
- [ ] FAIL — blocker found
- [ ] PARTIAL — more evidence required

Tester notes:

> 

## A. Baseline / no Overlay regression

- [ ] Open CinePulse normally.
- [ ] Render a known project with an empty Overlay scene.
- [ ] Output video/audio behavior matches the normal CinePulse path.
- [ ] No new Overlay error/log appears when no layer is active.

## B. PNG layer

- [ ] Add transparent PNG.
- [ ] Drag X/Y with mouse.
- [ ] Resize from handle.
- [ ] Opacity works.
- [ ] Z-order works with another layer.
- [ ] Lock prevents accidental movement.
- [ ] Off-canvas clipping behaves predictably.

## C. GIF layer

- [ ] Add animated GIF.
- [ ] Loop works for longer timeline.
- [ ] Speed control works.
- [ ] Resize preserves expected aspect.
- [ ] GIF stays aligned after preview seek.

## D. Music visualizers

- [ ] Waveform reacts naturally to real music.
- [ ] Bars react naturally to real music.
- [ ] Spectrum reacts naturally to real music.
- [ ] Sensitivity control is useful and stable.
- [ ] Thickness control changes the visual result.
- [ ] Bar count is respected.
- [ ] Mirror works.
- [ ] Primary/secondary colors are respected.
- [ ] Output audio remains correct and is not altered by the visualizer input path.

## E. Group / editor UX

- [ ] Select image/GIF + visualizer.
- [ ] Group them.
- [ ] Move group as one composition.
- [ ] Resize group proportionally.
- [ ] Group handle is clickable even in empty bounding-box area.
- [ ] Locked member prevents partial group deformation.
- [ ] Undo/redo behaves correctly.
- [ ] Quick layout presets are useful as starting points.

## F. Persistence

- [ ] Save preset and restore it.
- [ ] Add job to queue and reopen it.
- [ ] Close/reopen CinePulse and restore project/settings.
- [ ] Layer positions/sizes/styles remain identical.
- [ ] Missing PNG/GIF produces a clear blocking error instead of silently omitting the layer.

## G. DPI / display scaling

### Windows 100%
- [ ] Canvas coordinates match mouse.
- [ ] Resize handle matches visible position.
- [ ] No clipped property controls.

### Windows secondary scale (125% or 150%)
- [ ] Canvas coordinates match mouse.
- [ ] Resize/group handles match visible position.
- [ ] Text/property controls remain usable.
- [ ] No major layout overflow.

Observed scale / display:

> 

## H. Render matrix

| Scenario | Resolution | FPS | PNG | GIF | Visualizer | Audio | PASS/FAIL | Notes |
|---|---:|---:|---|---|---|---|---|---|
| Baseline | 1920x1080 | 30/60 | No | No | No | Yes | | |
| PNG + waveform | 1920x1080 | 60 | Yes | No | Waveform | Yes | | |
| GIF + bars | 1920x1080 | 60 | No | Yes | Bars | Yes | | |
| Mixed composition | 3840x2160 | 60 | Yes | Yes | Spectrum/Bars | Yes | | |
| Extreme smoke | 7680x4320 | target | Yes | optional | Visualizer | Yes | | |

## I. Visual/perceptual review

- [ ] Preview position approximately matches final render placement.
- [ ] PNG alpha edges look clean.
- [ ] GIF motion looks acceptable.
- [ ] Visualizer does not flicker unexpectedly.
- [ ] Visualizer scale looks appropriate beside character/art.
- [ ] Safe-area guide is useful for the intended platform.
- [ ] No obvious A/V sync issue introduced by the composition.

## J. Longform / soak

Recommended minimum before Stable discussion:

- [ ] 30 min real project completed.
- [ ] 1 h real project completed.
- [ ] 2 h real project completed or explicitly waived with reason.
- [ ] RAM remained bounded/acceptable.
- [ ] VRAM remained bounded/acceptable.
- [ ] GPU temperature remained acceptable for the machine.
- [ ] Free disk space did not collapse unexpectedly.
- [ ] Scratch did not grow as a `duration × FPS` Overlay frame sequence.
- [ ] Final file completed and opens correctly.

Soak notes / peaks:

> 

## K. Blocker classification

### S1 — Preview blocker
- crash;
- corrupted output;
- missing/wrong audio;
- scene cannot restore;
- severe overlay misalignment;
- uncontrolled disk growth;
- normal non-Overlay render regresses.

### S2 — serious
- major interaction bug;
- incorrect GIF/visualizer timing;
- DPI makes editing impractical;
- large preview/final mismatch.

### S3 — tolerable Preview defect
- workaround exists;
- minor preview artifact;
- small UX inconsistency.

### S4 — polish
- text/alignment/cosmetic improvement.

## Findings

| Severity | Area | Reproduction | Expected | Actual | Evidence file |
|---|---|---|---|---|---|
| | | | | | |

## Final recommendation

- [ ] Keep Draft / fix blockers
- [ ] Preview candidate — manual acceptance adequate
- [ ] Stable discussion allowed — all required physical gates passed

Signature / tester:

> 
"@
$checklist | Set-Content -LiteralPath $checklistPath -Encoding UTF8

if ($GenerateOnly) {
    Write-Host "CINEPULSE_OVERLAY_ACCEPTANCE_GENERATED $SessionRoot" -ForegroundColor Green
    if ($OpenFolder) { Start-Process explorer.exe $SessionRoot }
    return
}

if ($MonitorMinutes -gt 0) {
    if ($SampleSeconds -lt 5) { throw '-SampleSeconds deve ser pelo menos 5 segundos.' }
    $csvPath = Join-Path $SessionRoot 'soak-samples.csv'
    $samples = [System.Collections.Generic.List[object]]::new()
    $started = Get-Date
    $deadline = $started.AddMinutes($MonitorMinutes)
    Write-Host "OVERLAY SOAK MONITOR: $MonitorMinutes min, amostra a cada $SampleSeconds s" -ForegroundColor Cyan
    Write-Host "Evidence: $csvPath"

    while ((Get-Date) -lt $deadline) {
        $now = Get-Date
        $os = $null
        try { $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop } catch { }
        $proc = Get-ProcessSample -RequestedPid $ProcessId
        $gpu = Get-NvidiaSample
        $outputBytes = if ($OutputPath -and (Test-Path -LiteralPath $OutputPath)) { (Get-Item -LiteralPath $OutputPath).Length } else { $null }
        $scratchBytes = if ($ScratchPath) { Get-DirectorySizeBytes -Path $ScratchPath } else { $null }
        $targetDrive = $null
        try {
            $target = if ($OutputPath) { [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($OutputPath)) } else { [System.IO.Path]::GetPathRoot($ProjectRoot) }
            $targetDrive = Get-PSDrive -Name ($target.TrimEnd('\').TrimEnd(':')) -ErrorAction SilentlyContinue
        } catch { }

        $sample = [pscustomobject]@{
            timestamp = $now.ToUniversalTime().ToString('o')
            elapsed_seconds = [math]::Round(($now - $started).TotalSeconds, 1)
            free_memory_gb = if ($os) { [math]::Round(($os.FreePhysicalMemory * 1KB / 1GB), 3) } else { $null }
            process_count = if ($proc) { $proc.process_count } else { 0 }
            process_working_set_mb = if ($proc) { $proc.working_set_mb } else { $null }
            process_private_memory_mb = if ($proc) { $proc.private_memory_mb } else { $null }
            process_cpu_seconds = if ($proc) { $proc.cpu_seconds } else { $null }
            gpu_name = if ($gpu) { $gpu.name } else { $null }
            gpu_utilization_percent = if ($gpu) { $gpu.utilization_percent } else { $null }
            gpu_memory_used_mb = if ($gpu) { $gpu.memory_used_mb } else { $null }
            gpu_memory_total_mb = if ($gpu) { $gpu.memory_total_mb } else { $null }
            gpu_temperature_c = if ($gpu) { $gpu.temperature_c } else { $null }
            output_size_gb = Convert-BytesToGb $outputBytes
            scratch_size_gb = Convert-BytesToGb $scratchBytes
            target_drive_free_gb = if ($targetDrive -and $null -ne $targetDrive.Free) { Convert-BytesToGb $targetDrive.Free } else { $null }
        }
        $samples.Add($sample)
        $sample | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Append -Encoding UTF8
        Write-Host ("[{0:HH:mm:ss}] RAM free={1}GB GPU={2}% VRAM={3}MB temp={4}C appWS={5}MB" -f $now, $sample.free_memory_gb, $sample.gpu_utilization_percent, $sample.gpu_memory_used_mb, $sample.gpu_temperature_c, $sample.process_working_set_mb)
        Start-Sleep -Seconds $SampleSeconds
    }

    $summary = [ordered]@{
        schema = 'cinepulse.overlay-soak-summary/1'
        started_at = $started.ToUniversalTime().ToString('o')
        finished_at = (Get-Date).ToUniversalTime().ToString('o')
        requested_minutes = $MonitorMinutes
        samples = $samples.Count
        min_free_memory_gb = if ($samples.Count) { ($samples | Measure-Object -Property free_memory_gb -Minimum).Minimum } else { $null }
        max_process_working_set_mb = if ($samples.Count) { ($samples | Measure-Object -Property process_working_set_mb -Maximum).Maximum } else { $null }
        max_gpu_memory_used_mb = if ($samples.Count) { ($samples | Measure-Object -Property gpu_memory_used_mb -Maximum).Maximum } else { $null }
        max_gpu_temperature_c = if ($samples.Count) { ($samples | Measure-Object -Property gpu_temperature_c -Maximum).Maximum } else { $null }
        max_scratch_size_gb = if ($samples.Count) { ($samples | Measure-Object -Property scratch_size_gb -Maximum).Maximum } else { $null }
        final_output_size_gb = if ($samples.Count) { $samples[$samples.Count - 1].output_size_gb } else { $null }
    }
    $summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $SessionRoot 'soak-summary.json') -Encoding UTF8
    Write-Host "CINEPULSE_OVERLAY_SOAK_COMPLETE $SessionRoot" -ForegroundColor Green
} else {
    Write-Host 'Environment/checklist generated. Use -MonitorMinutes N in a second PowerShell window during a long render.' -ForegroundColor Yellow
}

if ($OpenFolder) { Start-Process explorer.exe $SessionRoot }
Write-Host "CINEPULSE_OVERLAY_ACCEPTANCE_READY $SessionRoot" -ForegroundColor Green
