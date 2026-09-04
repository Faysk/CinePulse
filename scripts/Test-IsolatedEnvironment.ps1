[CmdletBinding()]
param(
    [string]$Python = ''
)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$EnvScript = Join-Path $Root 'installer\CinePulse-Environment.cmd'
if (-not (Test-Path -LiteralPath $EnvScript)) { throw 'CinePulse-Environment.cmd not found.' }
if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
$Python = (Resolve-Path -LiteralPath $Python).Path

$Probe = @'
import json, os, tempfile
keys = [
    "CINEPULSE_ROOT", "CINEPULSE_DATA_DIR", "CINEPULSE_COMPONENTS_DIR",
    "CINEPULSE_CACHE_DIR", "CINEPULSE_TEMP_DIR", "TEMP", "TMP", "TMPDIR",
    "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR", "PIP_CACHE_DIR", "TORCH_HOME",
    "XDG_CACHE_HOME", "HF_HOME", "NUMBA_CACHE_DIR", "MPLCONFIGDIR",
    "PYTHONPYCACHEPREFIX"
]
payload = {key: os.environ.get(key, "") for key in keys}
payload["tempfile"] = tempfile.gettempdir()
print(json.dumps(payload))
'@
$ProbePath = Join-Path $Root 'temp\installer-v2-env-probe.py'
New-Item -ItemType Directory -Path (Split-Path -Parent $ProbePath) -Force | Out-Null
Set-Content -LiteralPath $ProbePath -Value $Probe -Encoding UTF8
try {
    $EscapedEnv = $EnvScript.Replace('"', '""')
    $EscapedPython = $Python.Replace('"', '""')
    $EscapedProbe = $ProbePath.Replace('"', '""')
    $Output = & cmd.exe /D /S /C "call `"$EscapedEnv`" && `"$EscapedPython`" `"$EscapedProbe`""
    if ($LASTEXITCODE -ne 0) { throw "Environment probe failed with exit code $LASTEXITCODE." }
    $Payload = $Output | Select-Object -Last 1 | ConvertFrom-Json
    $CanonicalRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    foreach ($Property in $Payload.PSObject.Properties) {
        if (-not $Property.Value) { throw "Environment variable $($Property.Name) is empty." }
        $Resolved = [IO.Path]::GetFullPath([string]$Property.Value)
        if (-not $Resolved.StartsWith($CanonicalRoot, [StringComparison]::OrdinalIgnoreCase) -and $Resolved.TrimEnd('\') -ne $Root.TrimEnd('\')) {
            throw "$($Property.Name) escaped CinePulse root: $Resolved"
        }
    }
    if ([IO.Path]::GetFullPath([string]$Payload.tempfile) -ne [IO.Path]::GetFullPath((Join-Path $Root 'temp'))) {
        throw "Python tempfile is not using CinePulse temp: $($Payload.tempfile)"
    }
    Write-Host "CINEPULSE_ISOLATED_ENVIRONMENT_OK root=$Root tempfile=$($Payload.tempfile)"
}
finally {
    Remove-Item -LiteralPath $ProbePath -Force -ErrorAction SilentlyContinue
}
