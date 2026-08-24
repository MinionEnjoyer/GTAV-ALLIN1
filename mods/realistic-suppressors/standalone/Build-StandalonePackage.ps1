[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$standaloneRoot = Split-Path -Parent $PSCommandPath
$modRoot = Split-Path -Parent $standaloneRoot
$repoRoot = Split-Path -Parent (Split-Path -Parent $modRoot)
$project = Join-Path $modRoot 'RealisticSuppressors.csproj'
$buildRoot = Join-Path $standaloneRoot '.build'
$packageRoot = Join-Path $buildRoot 'package'
$distRoot = Join-Path $standaloneRoot 'dist'
$version = '1.1.0'
$packageName = "Suppressors-Enhanced-Standalone-$version"
$supersededPackage = Join-Path $distRoot "RealisticSuppressors-Standalone-$version.oiv"

if (Test-Path -LiteralPath $buildRoot) {
    $resolvedBuild = (Resolve-Path -LiteralPath $buildRoot).Path
    $resolvedStandalone = (Resolve-Path -LiteralPath $standaloneRoot).Path
    if (-not $resolvedBuild.StartsWith(
            $resolvedStandalone + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear unexpected build directory: $resolvedBuild"
    }
    Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
}

& dotnet build $project -c Release --nologo -p:StandaloneBuild=true
if ($LASTEXITCODE -ne 0) {
    throw 'Standalone RealisticSuppressors.dll build failed.'
}

$scriptFolder = Join-Path $packageRoot 'content\scripts\RealisticSuppressors'
$dlcFolder = Join-Path $packageRoot 'content\mods\update\x64\dlcpacks\rs_suppressor_heat'
New-Item -ItemType Directory -Path $scriptFolder -Force | Out-Null
New-Item -ItemType Directory -Path $dlcFolder -Force | Out-Null
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
if (Test-Path -LiteralPath $supersededPackage) {
    Remove-Item -LiteralPath $supersededPackage -Force
}

Copy-Item -LiteralPath (Join-Path $standaloneRoot 'assembly.xml') `
    -Destination (Join-Path $packageRoot 'assembly.xml') -Force
Copy-Item -LiteralPath (Join-Path $standaloneRoot 'README.md') `
    -Destination (Join-Path $packageRoot 'README-Standalone.md') -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'CREDITS.md') `
    -Destination (Join-Path $packageRoot 'CREDITS.md') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'LICENSE') `
    -Destination (Join-Path $packageRoot 'LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $standaloneRoot 'payload\RealisticSuppressors.dll') `
    -Destination (Join-Path $scriptFolder 'RealisticSuppressors.dll') -Force
Copy-Item -LiteralPath (Join-Path $standaloneRoot 'RealisticSuppressors.ini.example') `
    -Destination (Join-Path $scriptFolder 'RealisticSuppressors.ini.example') -Force
Copy-Item -LiteralPath (Join-Path $modRoot 'payload\rs_suppressor_heat\dlc.rpf') `
    -Destination (Join-Path $dlcFolder 'dlc.rpf') -Force

$zipPath = Join-Path $buildRoot ($packageName + '.zip')
$oivPath = Join-Path $distRoot ($packageName + '.oiv')
if (Test-Path -LiteralPath $oivPath) {
    Remove-Item -LiteralPath $oivPath -Force
}
Compress-Archive -Path (Join-Path $packageRoot '*') `
    -DestinationPath $zipPath -CompressionLevel Optimal
Move-Item -LiteralPath $zipPath -Destination $oivPath -Force

$dllHash = (Get-FileHash -Algorithm SHA256 -LiteralPath `
    (Join-Path $scriptFolder 'RealisticSuppressors.dll')).Hash
$dlcHash = (Get-FileHash -Algorithm SHA256 -LiteralPath `
    (Join-Path $dlcFolder 'dlc.rpf')).Hash
$oivHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $oivPath).Hash

Remove-Item -LiteralPath $buildRoot -Recurse -Force

Write-Output "Built $oivPath"
Write-Output "Standalone DLL SHA256: $dllHash"
Write-Output "Heat DLC SHA256: $dlcHash"
Write-Output "OIV SHA256: $oivHash"
