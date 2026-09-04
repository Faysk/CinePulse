[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ProjectRoot,
    [Parameter(Mandatory)][string]$RuntimeRoot
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$RuntimeRoot = [IO.Path]::GetFullPath($RuntimeRoot)
$PendingFile = Join-Path $RuntimeRoot 'pending-update.json'
if (-not (Test-Path -LiteralPath $PendingFile)) { return }

if ($env:CINEPULSE_PORTABLE -ne '1' -and -not (Test-Path -LiteralPath (Join-Path $ProjectRoot '.cinepulse-portable'))) {
    throw 'Atualização in-place é suportada somente no pacote portátil; use o MSI para atualizar a instalação instalada.'
}

$ProtectedTopLevel = @('.runtime', 'components', 'data', 'cache', 'temp', '.git', 'dist')

function Get-ManagedTopLevelEntries {
    param([Parameter(Mandatory)][string]$Root)
    if (-not (Test-Path -LiteralPath $Root)) { return @() }
    return @(
        Get-ChildItem -LiteralPath $Root -Force |
            Where-Object { $_.Name -notin $ProtectedTopLevel }
    )
}

function Assert-PathInside {
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][string]$Candidate,
        [Parameter(Mandatory)][string]$Message
    )
    $ResolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    $ResolvedCandidate = [IO.Path]::GetFullPath($Candidate)
    $Prefix = $ResolvedRoot + '\'
    if ($ResolvedCandidate -ne $ResolvedRoot -and -not $ResolvedCandidate.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw $Message
    }
}

function Test-PackageManifest {
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
    foreach ($Item in $Manifest.files) {
        $Relative = ([string]$Item.path).Replace('/', '\').TrimStart('\')
        if (-not $Relative) { throw 'Manifesto contém caminho vazio.' }
        $First = $Relative.Split('\', 2)[0]
        if ($First -in $ProtectedTopLevel) { throw "Pacote tenta escrever em área mutável/protegida: $Relative" }
        $Target = [IO.Path]::GetFullPath((Join-Path $PackageRoot $Relative))
        Assert-PathInside -Root $PackageRoot -Candidate $Target -Message "Manifesto contém caminho inseguro: $Relative"
        if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) { throw "Arquivo do manifesto ausente: $Relative" }
        $Info = Get-Item -LiteralPath $Target
        if ([int64]$Item.size -ne $Info.Length) { throw "Tamanho divergente no pacote: $Relative" }
        $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash.ToLowerInvariant()
        if ($Hash -ne ([string]$Item.sha256).ToLowerInvariant()) { throw "SHA-256 divergente no pacote: $Relative" }
    }
    foreach ($Required in @('CinePulse.cmd', 'Install-CinePulse.cmd', 'pyproject.toml', 'installer\Start-CinePulse.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $PackageRoot $Required))) { throw "Pacote de atualização incompleto: $Required" }
    }
    return $Manifest
}

$Pending = Get-Content -LiteralPath $PendingFile -Raw | ConvertFrom-Json
if ($Pending.schema -ne 1 -or -not $Pending.source -or -not $Pending.version) {
    throw 'A atualização pendente possui metadados inválidos.'
}
$UpdatesRoot = [IO.Path]::GetFullPath((Join-Path $RuntimeRoot 'updates'))
$Source = [IO.Path]::GetFullPath([string]$Pending.source)
Assert-PathInside -Root $UpdatesRoot -Candidate $Source -Message 'A origem da atualização não pertence à pasta privada do CinePulse.'
if (-not (Test-Path -LiteralPath $Source -PathType Container)) { throw 'A origem da atualização não existe.' }

# Validate every managed incoming file before the current installation is touched.
$null = Test-PackageManifest -PackageRoot $Source -ExpectedVersion ([string]$Pending.version)

$Backup = Join-Path $RuntimeRoot 'update-backup'
if (Test-Path -LiteralPath $Backup) { Remove-Item -LiteralPath $Backup -Recurse -Force }
New-Item -ItemType Directory -Path $Backup -Force | Out-Null
$BackupComplete = $false
$DestructivePhaseStarted = $false
try {
    foreach ($Entry in Get-ManagedTopLevelEntries -Root $ProjectRoot) {
        Copy-Item -LiteralPath $Entry.FullName -Destination (Join-Path $Backup $Entry.Name) -Recurse -Force
    }
    $BackupComplete = $true

    # Replace the complete managed payload, rather than overlay-copying it. This
    # removes files deleted by the new version and prevents mixed-version trees.
    $DestructivePhaseStarted = $true
    foreach ($Entry in Get-ManagedTopLevelEntries -Root $ProjectRoot) {
        Remove-Item -LiteralPath $Entry.FullName -Recurse -Force
    }

    if ($env:CINEPULSE_CI_UPDATE_FAIL_AFTER_REMOVE -eq '1') {
        throw 'Falha injetada após remoção do payload gerenciado.'
    }

    foreach ($Entry in Get-ManagedTopLevelEntries -Root $Source) {
        Copy-Item -LiteralPath $Entry.FullName -Destination (Join-Path $ProjectRoot $Entry.Name) -Recurse -Force
    }

    if ($env:CINEPULSE_CI_UPDATE_FAIL_AFTER_COPY -eq '1') {
        throw 'Falha injetada após cópia do payload recebido.'
    }

    # Verify the tree after copying as a second integrity boundary.
    $null = Test-PackageManifest -PackageRoot $ProjectRoot -ExpectedVersion ([string]$Pending.version)

    Remove-Item -LiteralPath $PendingFile -Force
    $VersionRoot = Split-Path -Parent (Split-Path -Parent $Source)
    if (Test-Path -LiteralPath $VersionRoot) { Remove-Item -LiteralPath $VersionRoot -Recurse -Force }
    Remove-Item -LiteralPath $Backup -Recurse -Force
    Write-Host "CINEPULSE_UPDATE_APPLY_OK version=$($Pending.version) rollback=armed"
}
catch {
    $Failure = $_
    if ($BackupComplete -and $DestructivePhaseStarted) {
        try {
            foreach ($Entry in Get-ManagedTopLevelEntries -Root $ProjectRoot) {
                Remove-Item -LiteralPath $Entry.FullName -Recurse -Force
            }
            foreach ($Entry in Get-ChildItem -LiteralPath $Backup -Force) {
                Copy-Item -LiteralPath $Entry.FullName -Destination (Join-Path $ProjectRoot $Entry.Name) -Recurse -Force
            }
            Write-Host 'CINEPULSE_UPDATE_ROLLBACK_OK previous-payload=restored'
        }
        catch {
            throw "A atualização falhou e o rollback também falhou. Backup preservado em $Backup. Erro original: $($Failure.Exception.Message). Erro de rollback: $($_.Exception.Message)"
        }
    }
    throw "A atualização falhou e a versão anterior foi restaurada. $($Failure.Exception.Message)"
}
