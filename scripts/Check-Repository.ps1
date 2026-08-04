[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Failures = [System.Collections.Generic.List[string]]::new()
$IgnoredRoots = @('.git', '.runtime', '.venv', 'components', 'data')
$MaxBytes = 90MB

Get-ChildItem -LiteralPath $ProjectRoot -File -Recurse -Force | ForEach-Object {
    $Relative = $_.FullName.Substring($ProjectRoot.Length).TrimStart('\')
    $Top = ($Relative -split '\\')[0]
    if ($Top -in $IgnoredRoots) { return }
    if ($_.Length -gt $MaxBytes) {
        $Failures.Add("Arquivo maior que 90 MiB: $Relative")
    }
    if ($_.Extension -in @('.pth', '.pt', '.ckpt', '.safetensors', '.onnx', '.pkl')) {
        $Failures.Add("Peso de modelo no repositório: $Relative")
    }
}

Get-ChildItem -LiteralPath $ProjectRoot -Directory -Recurse -Force |
    Where-Object { $_.Name -eq '.git' -and $_.FullName -ne (Join-Path $ProjectRoot '.git') } |
    ForEach-Object { $Failures.Add("Repositório Git aninhado: $($_.FullName)") }

if ($Failures.Count) {
    $Failures | ForEach-Object { Write-Error $_ -ErrorAction Continue }
    exit 1
}

Write-Host 'CINEPULSE_REPOSITORY_CHECK_OK'

