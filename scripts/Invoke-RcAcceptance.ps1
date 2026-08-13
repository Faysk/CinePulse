[CmdletBinding()]
param(
    [string]$Version = '1.0.0-rc.5',
    [switch]$SkipBuilds,
    [switch]$RunGpu,
    [switch]$RunMsiLifecycle
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$EvidenceRoot = Join-Path $ProjectRoot 'artifacts\rc-acceptance'
New-Item -ItemType Directory -Path $EvidenceRoot -Force | Out-Null

$PythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
if (-not $PythonCommand) { $PythonCommand = Get-Command 'py' -ErrorAction SilentlyContinue }
if (-not $PythonCommand) { throw 'Python não encontrado para executar o aceite RC.' }
$Python = $PythonCommand.Source
$env:PYTHONPATH = (Join-Path $ProjectRoot 'src')

$Steps = [System.Collections.Generic.List[object]]::new()
function Invoke-AcceptanceStep {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][scriptblock]$Action
    )
    $Started = Get-Date
    Write-Host "`n=== RC ACCEPTANCE: $Name ===" -ForegroundColor Cyan
    try {
        & $Action
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$Name terminou com código $LASTEXITCODE" }
        $Steps.Add([pscustomobject]@{ name=$Name; passed=$true; seconds=[math]::Round(((Get-Date)-$Started).TotalSeconds,3); error=$null })
    } catch {
        $Steps.Add([pscustomobject]@{ name=$Name; passed=$false; seconds=[math]::Round(((Get-Date)-$Started).TotalSeconds,3); error=$_.Exception.Message })
        throw
    }
}

$Passed = $false
try {
    Invoke-AcceptanceStep 'static-final-audit' {
        & $Python (Join-Path $PSScriptRoot 'final_audit.py') --output (Join-Path $EvidenceRoot 'final-audit-static.json')
    }
    Invoke-AcceptanceStep 'release-light' {
        & $Python (Join-Path $PSScriptRoot 'ci_gate.py') --profile release-light --output (Join-Path $EvidenceRoot 'release-light-windows.json')
    }
    Invoke-AcceptanceStep 'powershell-release-contract' {
        & (Join-Path $PSScriptRoot 'Test-Release.ps1')
    }

    if (-not $SkipBuilds) {
        Invoke-AcceptanceStep 'portable-build' {
            & (Join-Path $PSScriptRoot 'Build-Portable.ps1') -Version $Version -BuildPython $Python -SkipTests
        }
        Invoke-AcceptanceStep 'portable-updater' {
            & (Join-Path $PSScriptRoot 'Test-Updater.ps1') -Version $Version
        }
        Invoke-AcceptanceStep 'msi-build' {
            & (Join-Path $PSScriptRoot 'Build-Msi.ps1') -Version $Version -BuildPython $Python -SkipTests
        }
        Invoke-AcceptanceStep 'msi-payload' {
            & (Join-Path $PSScriptRoot 'Test-Msi.ps1') -Version $Version
        }
    }

    if ($RunMsiLifecycle) {
        if ($SkipBuilds) { throw '-RunMsiLifecycle exige que o MSI seja construído; remova -SkipBuilds.' }
        Invoke-AcceptanceStep 'msi-lifecycle' {
            $Old = $env:CINEPULSE_CI_ALLOW_MSI_LIFECYCLE
            try {
                $env:CINEPULSE_CI_ALLOW_MSI_LIFECYCLE = '1'
                & (Join-Path $PSScriptRoot 'Test-MsiLifecycle.ps1') -Version $Version
            } finally {
                $env:CINEPULSE_CI_ALLOW_MSI_LIFECYCLE = $Old
            }
        }
    }

    if ($RunGpu) {
        Invoke-AcceptanceStep 'nvidia-inventory' { nvidia-smi }
        Invoke-AcceptanceStep 'gpu-gate' {
            & $Python (Join-Path $PSScriptRoot 'ci_gate.py') --profile gpu --output (Join-Path $EvidenceRoot 'gpu-windows.json')
        }
    }
    $Passed = $true
} finally {
    $Payload = [ordered]@{
        schema = 1
        version = $Version
        computer = $env:COMPUTERNAME
        windows = [Environment]::OSVersion.VersionString
        finished_at = (Get-Date).ToUniversalTime().ToString('o')
        passed = $Passed
        gpu_requested = [bool]$RunGpu
        msi_lifecycle_requested = [bool]$RunMsiLifecycle
        steps = @($Steps)
        manual_acceptance_still_required = @(
            'render musical longo com mídia real',
            '8K/120 na máquina-alvo',
            'inspeção visual HDR/tone mapping em monitor adequado',
            'fila real com múltiplos projetos',
            'qualidade perceptiva de VFX/transições e emendas neurais'
        )
    }
    $JsonPath = Join-Path $EvidenceRoot 'rc-acceptance-windows.json'
    $Payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $JsonPath -Encoding UTF8
    Write-Host "CINEPULSE_RC_ACCEPTANCE_REPORT $JsonPath"
}

if (-not $Passed) { exit 1 }
Write-Host 'CINEPULSE_RC_AUTOMATED_ACCEPTANCE_OK' -ForegroundColor Green
