[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ReactorRoot,

    [string]$PackageRoot = (Join-Path $PSScriptRoot '..\.work\ReactorV-0.2.0-ALLIN1'),

    [string]$Version = '0.2.0'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot '.work'))
$resolvedPackageRoot = [IO.Path]::GetFullPath($PackageRoot)
$workPrefix = $workRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
    [IO.Path]::DirectorySeparatorChar
if (-not $resolvedPackageRoot.StartsWith(
        $workPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
    throw "Refusing to synchronize a package outside the repository .work directory: $resolvedPackageRoot"
}

$stagingRoot = [IO.Path]::GetFullPath((Join-Path $ReactorRoot 'artifacts\staging'))
if (-not (Test-Path -LiteralPath $stagingRoot -PathType Container)) {
    throw "Reactor staging output was not found: $stagingRoot"
}

$contentManifest = Join-Path $resolvedPackageRoot 'allin1.content.json'
if (-not (Test-Path -LiteralPath $contentManifest -PathType Leaf)) {
    throw "The ALLIN1 content manifest is missing: $contentManifest"
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

    return [IO.Path]::GetRelativePath($Base, $Path).Replace('\', '/')
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
