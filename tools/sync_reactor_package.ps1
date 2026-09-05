[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ReactorRoot,

    [string]$PackageRoot = '',

    [string]$Version = '0.2.0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.work'))
if ([string]::IsNullOrWhiteSpace($PackageRoot)) {
    $PackageRoot = Join-Path $workRoot 'ReactorV-0.2.0-ALLIN1'
}
$resolvedPackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$workPrefix = $workRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
if (-not $resolvedPackageRoot.StartsWith(
        $workPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
    throw "Refusing to synchronize a package outside the repository .work directory: $resolvedPackageRoot"
}
New-Item -ItemType Directory -Path $resolvedPackageRoot -Force | Out-Null

$stagingRoot = [IO.Path]::GetFullPath((Join-Path $ReactorRoot 'artifacts\staging'))
if (-not (Test-Path -LiteralPath $stagingRoot -PathType Container)) {
    throw "Reactor staging output was not found: $stagingRoot"
}

$allowedPackageEntries = @('mod.toml', 'allin1.content.json', 'payload')
$unexpectedPackageEntries = @(
    Get-ChildItem -LiteralPath $resolvedPackageRoot -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin $allowedPackageEntries }
)
if ($unexpectedPackageEntries) {
    throw (
        "The Reactor package workspace contains unowned files. Move snapshots " +
        "outside the package root before synchronization:`n" +
        ($unexpectedPackageEntries.FullName -join "`n")
    )
}

$unexpectedStagingEntries = @(
    Get-ChildItem -LiteralPath $stagingRoot -Force -Recurse |
        Where-Object {
            ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            (-not $_.PSIsContainer -and (
                $_.Name -like '*Harness*' -or
                $_.Extension -in @('.map', '.pdb', '.log', '.tmp')
            )) -or
            ($_.PSIsContainer -and $_.Name -eq 'node_modules')
        }
)
if ($unexpectedStagingEntries) {
    throw "Reactor staging contains development artifacts:`n$($unexpectedStagingEntries.FullName -join "`n")"
}

$contentManifest = Join-Path $resolvedPackageRoot 'allin1.content.json'
$contentContract = [ordered]@{
    schema_version = 1
    api_version = 1
    id = 'ragewebui.framework'
    name = 'REACTOR V'
    version = $Version
    description = 'Native HTML and React overlay framework for GTA V Story Mode using Direct3D 11 or Direct3D 12.'
    capabilities = @(
        'story.web-overlay'
        'story.telemetry'
        'story.actions'
        'story.api-v2'
        'story.extensions'
        'story.menus'
        'story.menu-presentation'
        'story.menu-bound-parameters'
        'story.events'
        'story.lifecycle'
        'story.semantic-input'
    )
    systems = @()
    gbay = [ordered]@{
        sections = @()
        catalogs = @()
    }
    runtime = [ordered]@{
        assemblies = @(
            [ordered]@{
                path = 'scripts/ReactorV/RageWebUI.Script.dll'
                entry_point = 'RageWebUI.Script.RageWebUiScript'
            }
        )
    }
}
$contentEncoding = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText(
    $contentManifest,
    ($contentContract | ConvertTo-Json -Depth 8) + [Environment]::NewLine,
    $contentEncoding
)
$content = Get-Content -LiteralPath $contentManifest -Raw | ConvertFrom-Json
if (
    $content.id -ne 'ragewebui.framework' -or
    $content.version -ne $Version
) {
    throw (
        "Reactor content contract mismatch: expected ragewebui.framework " +
        "$Version, found $($content.id) $($content.version)."
    )
}

$payloadRoot = Join-Path $resolvedPackageRoot 'payload'
if (Test-Path -LiteralPath $payloadRoot) {
    Remove-Item -LiteralPath $payloadRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $payloadRoot -Force | Out-Null
Get-ChildItem -LiteralPath $stagingRoot -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $payloadRoot -Recurse -Force
}

function Get-RelativePackagePath {
    param(
        [Parameter(Mandatory)] [string]$Base,
        [Parameter(Mandatory)] [string]$Path
    )

    # Windows PowerShell 5.1 runs on .NET Framework, which does not expose
    # Path.GetRelativePath. Both paths are package-owned and must remain under
    # the same payload root, so a validated prefix is clearer and portable.
    $baseFull = [IO.Path]::GetFullPath($Base).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    ) + [IO.Path]::DirectorySeparatorChar
    $pathFull = [IO.Path]::GetFullPath($Path)
    if (-not $pathFull.StartsWith(
            $baseFull,
            [StringComparison]::OrdinalIgnoreCase
        )) {
        throw "Package file is outside the synchronized payload root: $pathFull"
    }
    return $pathFull.Substring($baseFull.Length).Replace('\', '/')
}

function Add-FileRecord {
    param(
        [Collections.Generic.List[string]]$Lines,
        [Parameter(Mandatory)] [string]$Source,
        [Parameter(Mandatory)] [string]$Destination,
        [Parameter(Mandatory)] [string]$FilePath
    )

    if ($null -eq $Lines) {
        throw 'Manifest line collection was not supplied.'
    }
    $hash = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $Lines.Add('')
    $Lines.Add('[[files]]')
    $Lines.Add("source = `"$Source`"")
    $Lines.Add("destination = `"$Destination`"")
    $Lines.Add("sha256 = `"$hash`"")
}

$lines = [Collections.Generic.List[string]]::new()
$lines.Add('schema_version = 2')
$lines.Add('id = "ragewebui.framework"')
$lines.Add('name = "REACTOR V"')
$lines.Add("version = `"$Version`"")
$lines.Add('type = "mixed"')
$lines.Add('description = "REACTOR V is a checksum-pinned HTML and React overlay framework for GTA V Story Mode. It selects the safest compatible renderer for the active script host."')
$lines.Add('editions = ["legacy", "enhanced"]')
$lines.Add('dependencies = ["scripthookv", "shvdn"]')
$lines.Add('conflicts = []')
$lines.Add('')
$lines.Add('[allin1]')
$lines.Add('api_version = 1')
$lines.Add('content = "allin1.content.json"')
$lines.Add('requires = []')

$contentRecord = @{
    Lines = $lines
    Source = 'allin1.content.json'
    Destination = 'scripts/ReactorV/allin1.content.json'
    FilePath = $contentManifest
}
Add-FileRecord @contentRecord

$stagedFiles = @(
    Get-ChildItem -LiteralPath $payloadRoot -File -Recurse |
        Sort-Object { Get-RelativePackagePath -Base $payloadRoot -Path $_.FullName }
)
foreach ($file in $stagedFiles) {
    $relative = Get-RelativePackagePath -Base $payloadRoot -Path $file.FullName
    $payloadRecord = @{
        Lines = $lines
        Source = "payload/$relative"
        Destination = $relative
        FilePath = $file.FullName
    }
    Add-FileRecord @payloadRecord
}

$manifestPath = Join-Path $resolvedPackageRoot 'mod.toml'
$encoding = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText(
    $manifestPath,
    ($lines -join [Environment]::NewLine) + [Environment]::NewLine,
    $encoding
)

Write-Host "Synchronized $($stagedFiles.Count) Reactor payload files."
Write-Host "Generated: $manifestPath"

$python = Join-Path $repositoryRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "The ALLIN1 validation environment is missing: $python"
}
& $python -m allin1.cli content validate $resolvedPackageRoot
if ($LASTEXITCODE -ne 0) {
    throw "The synchronized Reactor package failed ALLIN1 validation."
}
