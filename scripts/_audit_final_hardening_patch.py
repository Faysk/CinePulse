from pathlib import Path
import re

start_path = Path('installer/Start-CinePulse.ps1')
start = start_path.read_text(encoding='utf-8-sig')


def replace_block(text: str, begin: str, end: str, replacement: str, label: str) -> str:
    pattern = re.compile(re.escape(begin) + r'.*?(?=' + re.escape(end) + r')', re.S)
    value = replacement.rstrip() + '\n\n'
    updated, count = pattern.subn(lambda _m: value, text, count=1)
    if count != 1:
        raise SystemExit(f'{label}: expected one block, got {count}')
    return updated


start = replace_block(
    start,
    'function Get-PortableUv {',
    'function Install-PortableFfmpeg {',
    r'''function Get-PortableUv {
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
}''',
    'uv cache identity',
)

old = "$ExpectedPythonVersion = [string]$BootstrapManifest.python.version\n$RebuildRuntime = $Repair -or -not (Test-Path -LiteralPath $PythonExe)"
new = "$ExpectedPythonVersion = [string]$BootstrapManifest.python.version\n$RuntimeRebuilt = $false\n$RebuildRuntime = $Repair -or -not (Test-Path -LiteralPath $PythonExe)"
if old not in start:
    raise SystemExit('runtime rebuilt initialization pattern missing')
start = start.replace(old, new, 1)

old = "    & $UvExe venv --python $ExpectedPythonVersion --python-preference only-managed $VenvRoot\n    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar o Python gerenciado do CinePulse.' }\n}"
new = "    & $UvExe venv --python $ExpectedPythonVersion --python-preference only-managed $VenvRoot\n    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível preparar o Python gerenciado do CinePulse.' }\n    $RuntimeRebuilt = $true\n}"
if old not in start:
    raise SystemExit('runtime rebuilt success pattern missing')
start = start.replace(old, new, 1)

old = "$CurrentState = if (Test-Path -LiteralPath $InstallState) { Get-Content -LiteralPath $InstallState -Raw } else { '' }\nif ($InstallOnly) { Write-Host '[2/4] Verificando dependências do CinePulse...' }\nif ($Repair -or $CurrentState.Trim() -ne $ExpectedState.Trim()) {"
new = "$CurrentState = if (Test-Path -LiteralPath $InstallState) { Get-Content -LiteralPath $InstallState -Raw } else { '' }\n$RuntimePackagesHealthy = $false\nif (-not $RuntimeRebuilt) {\n    try {\n        & $PythonExe -c \"import numpy, cinepulse; raise SystemExit(0)\" *> $null\n        $RuntimePackagesHealthy = $LASTEXITCODE -eq 0\n    } catch {\n        $RuntimePackagesHealthy = $false\n    }\n}\nif ($InstallOnly) { Write-Host '[2/4] Verificando dependências do CinePulse...' }\nif ($Repair -or $RuntimeRebuilt -or -not $RuntimePackagesHealthy -or $CurrentState.Trim() -ne $ExpectedState.Trim()) {"
if old not in start:
    raise SystemExit('runtime package health pattern missing')
start = start.replace(old, new, 1)

start_path.write_text(start, encoding='utf-8-sig')

applier_path = Path('installer/Apply-CinePulseUpdate.ps1')
applier = applier_path.read_text(encoding='utf-8-sig')

pattern = re.compile(r"function Test-PackageManifest \{.*?\n\}\n\n\$Pending =", re.S)
replacement = r'''function Test-PackageManifest {
    param(
        [Parameter(Mandatory)][string]$PackageRoot,
        [Parameter(Mandatory)][string]$ExpectedVersion
    )
    $ManifestPath = Join-Path $PackageRoot 'cinepulse-files.json'
    if (-not (Test-Path -LiteralPath $ManifestPath)) { throw 'Pacote de atualização sem cinepulse-files.json.' }
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($Manifest.schema -ne 1 -or [string]$Manifest.version -ne $ExpectedVersion -or -not $Manifest.files) {
        throw "Manifesto do pacote incompatível com a atualização $ExpectedVersion."
    }
    $ManifestPaths = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($Item in $Manifest.files) {
        $Relative = ([string]$Item.path).Replace('\', '/').TrimStart('/')
        if (-not $Relative) { throw 'Manifesto contém caminho vazio.' }
        if (-not $ManifestPaths.Add($Relative)) { throw "Manifesto contém caminho duplicado: $Relative" }
        $First = $Relative.Split('/', 2)[0]
        if ($First -in $ProtectedTopLevel) { throw "Pacote tenta escrever em área mutável/protegida: $Relative" }
        $Target = [IO.Path]::GetFullPath((Join-Path $PackageRoot ($Relative.Replace('/', '\'))))
        Assert-PathInside -Root $PackageRoot -Candidate $Target -Message "Manifesto contém caminho inseguro: $Relative"
        if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw "Arquivo do manifesto ausente: $Relative" }
        $Info = Get-Item -LiteralPath $Target
        if ([int64]$Item.size -ne $Info.Length) { throw "Tamanho divergente no pacote: $Relative" }
        $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash.ToLowerInvariant()
        if ($Hash -ne ([string]$Item.sha256).ToLowerInvariant()) { throw "SHA-256 divergente no pacote: $Relative" }
    }
    foreach ($File in Get-ChildItem -LiteralPath $PackageRoot -File -Recurse) {
        $Relative = [IO.Path]::GetRelativePath($PackageRoot, $File.FullName).Replace('\', '/')
        if ($Relative -eq 'cinepulse-files.json') { continue }
        if (-not $ManifestPaths.Contains($Relative)) {
            throw "Pacote contém arquivo gerenciado não listado no manifesto: $Relative"
        }
    }
    foreach ($Required in @('CinePulse.cmd', 'Install-CinePulse.cmd', 'pyproject.toml', 'installer\Start-CinePulse.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $Required))) { throw "Pacote de atualização incompleto: $Required" }
    }
    return $Manifest
}

$Pending ='''
value = replacement.rstrip()
applier, count = pattern.subn(lambda _m: value, applier, count=1)
if count != 1:
    raise SystemExit(f'exact manifest block: expected one block, got {count}')
applier_path.write_text(applier, encoding='utf-8-sig')

print('CINEPULSE_FINAL_HARDENING_PATCH_OK')
