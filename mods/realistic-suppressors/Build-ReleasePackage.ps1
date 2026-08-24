[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$modRoot = Split-Path -Parent $PSCommandPath
$repoRoot = Split-Path -Parent (Split-Path -Parent $modRoot)
$buildRoot = Join-Path $modRoot '.release-build'
$distRoot = Join-Path $modRoot 'dist'
$version = '1.1.0'
$allin1Name = "Suppressors-Enhanced-ALLIN1-$version"
$standaloneName = "Suppressors-Enhanced-Standalone-$version"
$releaseName = "Suppressors-Enhanced-$version-Release"
$allin1Stage = Join-Path $buildRoot 'allin1'
$releaseStage = Join-Path $buildRoot 'release'
$project = Join-Path $modRoot 'RealisticSuppressors.csproj'
$standaloneBuilder = Join-Path $modRoot 'standalone\Build-StandalonePackage.ps1'
$cover = Join-Path $modRoot 'media\Suppressors-Enhanced-Cover.png'

if (Test-Path -LiteralPath $buildRoot) {
    $resolvedBuild = (Resolve-Path -LiteralPath $buildRoot).Path
    $resolvedMod = (Resolve-Path -LiteralPath $modRoot).Path
    if (-not $resolvedBuild.StartsWith(
            $resolvedMod + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear unexpected release build directory: $resolvedBuild"
    }
    Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
}

& dotnet build $project -c Release --nologo
if ($LASTEXITCODE -ne 0) {
    throw 'ALLIN1-hosted Suppressors Enhanced build failed.'
}
& $standaloneBuilder
if ($LASTEXITCODE -ne 0) {
    throw 'Standalone Suppressors Enhanced package build failed.'
}

New-Item -ItemType Directory -Path (Join-Path $allin1Stage 'payload') -Force | Out-Null
New-Item -ItemType Directory -Path `
    (Join-Path $allin1Stage 'payload\rs_suppressor_heat') -Force | Out-Null
New-Item -ItemType Directory -Path $releaseStage -Force | Out-Null
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $modRoot 'mod.toml') -Destination $allin1Stage -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'allin1.content.json') -Destination $allin1Stage -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'ALLIN1-README.md') `
    -Destination (Join-Path $allin1Stage 'README.md') -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'CREDITS.md') -Destination $allin1Stage -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'LICENSE') `
    -Destination (Join-Path $allin1Stage 'LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'payload\RealisticSuppressors.dll') `
    -Destination (Join-Path $allin1Stage 'payload\RealisticSuppressors.dll') -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'payload\rs_suppressor_heat\dlc.rpf') `
    -Destination (Join-Path $allin1Stage 'payload\rs_suppressor_heat\dlc.rpf') -Force

$allin1Archive = Join-Path $distRoot ($allin1Name + '.zip')
$standaloneSource = Join-Path $modRoot ('standalone\dist\' + $standaloneName + '.oiv')
$standaloneArchive = Join-Path $distRoot ($standaloneName + '.oiv')
$releaseArchive = Join-Path $distRoot ($releaseName + '.zip')
$checksumFile = Join-Path $distRoot 'SHA256SUMS.txt'
foreach ($target in @($allin1Archive, $standaloneArchive, $releaseArchive, $checksumFile)) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Force
    }
}

Compress-Archive -Path (Join-Path $allin1Stage '*') `
    -DestinationPath $allin1Archive -CompressionLevel Optimal
Copy-Item -LiteralPath $standaloneSource -Destination $standaloneArchive -Force

Copy-Item -LiteralPath $allin1Archive -Destination $releaseStage -Force
Copy-Item -LiteralPath $standaloneArchive -Destination $releaseStage -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'RELEASE.md') `
    -Destination (Join-Path $releaseStage 'README.md') -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'CREDITS.md') -Destination $releaseStage -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'LICENSE') `
    -Destination (Join-Path $releaseStage 'LICENSE.txt') -Force
Copy-Item -LiteralPath $cover `
    -Destination (Join-Path $releaseStage 'Suppressors-Enhanced-Cover.png') -Force

$innerChecksums = @(
    (Get-FileHash -Algorithm SHA256 -LiteralPath `
        (Join-Path $releaseStage ($allin1Name + '.zip'))),
    (Get-FileHash -Algorithm SHA256 -LiteralPath `
        (Join-Path $releaseStage ($standaloneName + '.oiv')))
) | ForEach-Object { "$($_.Hash)  $(Split-Path -Leaf $_.Path)" }
[IO.File]::WriteAllLines(
    (Join-Path $releaseStage 'SHA256SUMS.txt'),
    $innerChecksums,
    [Text.UTF8Encoding]::new($false))

Compress-Archive -Path (Join-Path $releaseStage '*') `
    -DestinationPath $releaseArchive -CompressionLevel Optimal

$outerChecksums = @(
    (Get-FileHash -Algorithm SHA256 -LiteralPath $allin1Archive),
    (Get-FileHash -Algorithm SHA256 -LiteralPath $standaloneArchive),
    (Get-FileHash -Algorithm SHA256 -LiteralPath $releaseArchive)
) | ForEach-Object { "$($_.Hash)  $(Split-Path -Leaf $_.Path)" }
[IO.File]::WriteAllLines(
    $checksumFile,
    $outerChecksums,
    [Text.UTF8Encoding]::new($false))

Remove-Item -LiteralPath $buildRoot -Recurse -Force

Write-Output "Built $allin1Archive"
Write-Output "Built $standaloneArchive"
Write-Output "Built $releaseArchive"
Write-Output "Checksums:"
Get-Content -LiteralPath $checksumFile
