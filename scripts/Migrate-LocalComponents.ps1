[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory=$true)]
    [string]$SourceTools
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$Source = (Resolve-Path -LiteralPath $SourceTools).Path
$Destination = Join-Path $ProjectRoot 'components'

if ($Source -match 'Senhor_da_Areia') {
    throw 'A pasta de render não pode ser usada como origem de componentes.'
}
if (-not (Test-Path -LiteralPath (Join-Path $Source 'real-esrgan')) -and -not (Test-Path -LiteralPath (Join-Path $Source 'ai'))) {
    throw 'A origem não contém componentes reconhecidos.'
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null
foreach ($Name in @('real-esrgan', 'ai')) {
    $Item = Join-Path $Source $Name
    if (Test-Path -LiteralPath $Item) {
        $Target = Join-Path $Destination $Name
        if ($PSCmdlet.ShouldProcess($Target, "Copiar componente local $Name")) {
            Copy-Item -LiteralPath $Item -Destination $Target -Recurse -Force
        }
    }
}

Write-Host 'Migração concluída. Os componentes permanecem fora do Git.'

