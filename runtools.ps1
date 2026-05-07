<#
.SYNOPSIS
    Downloads and builds the tools required by the ALLIN1 installer.

.DESCRIPTION
    Fetches gtautil.exe and builds YTDToolio.exe from source.
    All tools are placed in the tools/ directory.

    Prerequisites:
    - Visual Studio 2022 (with .NET and C++ desktop workloads)
    - Internet connection
    - Git

.EXAMPLE
    .\runtools.ps1
#>

$ErrorActionPreference = "Stop"
if ($PSScriptRoot) { $ScriptRoot = $PSScriptRoot } else { $ScriptRoot = (Get-Location).Path }
$ToolsDir = Join-Path $ScriptRoot "tools"

if (-not (Test-Path $ToolsDir)) {
    New-Item -ItemType Directory -Path $ToolsDir | Out-Null
}

$TempDir = Join-Path $ToolsDir "_build_temp"
if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# ---------------------------------------------------------------------
#  1. gtautil.exe  (indilo53/gtautil v2.2.7 - MIT license)
# ---------------------------------------------------------------------
Write-Host "`n[1/2] Downloading gtautil.exe..." -ForegroundColor Cyan

$GtautilDest = Join-Path $ToolsDir "gtautil.exe"
if (Test-Path $GtautilDest) {
    Write-Host "  Already exists, skipping."
} else {
    $GtautilZipUrl = "https://github.com/indilo53/gtautil/releases/download/2.2.7/gtautil-2.2.7.zip"
    $GtautilZip = Join-Path $TempDir "gtautil.zip"
    $GtautilExtract = Join-Path $TempDir "gtautil"

    Write-Host "  Downloading from $GtautilZipUrl"
    Invoke-WebRequest -Uri $GtautilZipUrl -OutFile $GtautilZip -UseBasicParsing

    Write-Host "  Extracting..."
    Expand-Archive -Path $GtautilZip -DestinationPath $GtautilExtract -Force

    # Find gtautil.exe in the extracted contents
    $GtautilExe = Get-ChildItem -Path $GtautilExtract -Filter "gtautil.exe" -Recurse | Select-Object -First 1
    if (-not $GtautilExe) {
        throw "gtautil.exe not found in downloaded archive"
    }
    Copy-Item $GtautilExe.FullName -Destination $GtautilDest
    Write-Host "  Saved to $GtautilDest" -ForegroundColor Green
}

# ---------------------------------------------------------------------
#  2. YTDToolio.exe  (kngrektor/ytdtool - built from source)
#     Reads PNG files directly and packs them into .ytd archives.
#     Uses RageLib for DXT compression internally.
# ---------------------------------------------------------------------
Write-Host "`n[2/2] Building YTDToolio.exe from source..." -ForegroundColor Cyan

$YtdtoolDest = Join-Path $ToolsDir "YTDToolio.exe"
if (Test-Path $YtdtoolDest) {
    Write-Host "  Already exists, skipping."
} else {
    $YtdtoolRepo = Join-Path $TempDir "ytdtool"

    # Clone with submodules (gta-toolkit provides RageLib)
    Write-Host "  Cloning kngrektor/ytdtool (with submodules)..."
    git clone --recursive "https://github.com/kngrektor/ytdtool.git" $YtdtoolRepo
    if ($LASTEXITCODE -ne 0) { throw "git clone failed" }

    # -- Locate MSBuild via vswhere --
    $VsWhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $VsWhere)) {
        throw "vswhere.exe not found. Install Visual Studio 2022."
    }
    $VsInstall = & $VsWhere -latest -property installationPath 2>$null
    if (-not $VsInstall) { throw "No Visual Studio installation found." }

    # Init VS developer environment (sets up cl.exe, msbuild paths, etc.)
    $VsDevCmd = Join-Path (Join-Path $VsInstall "Common7") "Tools\VsDevCmd.bat"
    if (-not (Test-Path $VsDevCmd)) {
        throw "VsDevCmd.bat not found. Visual Studio installation may be incomplete."
    }

    # Helper: run a command inside VS developer environment
    function Invoke-VsDev {
        param([string]$Command)
        $bat = Join-Path $TempDir "_vsdev.bat"
        Set-Content -Path $bat -Value "@echo off`r`ncall `"$VsDevCmd`" >nul 2>&1`r`n$Command"
        cmd /c $bat
        return $LASTEXITCODE
    }

    $ToolkitDir = Join-Path (Join-Path $YtdtoolRepo "vendor") "gta-toolkit"

    # -- Step A: Patch gta-toolkit (remove DirectXTex dependency) --
    # This mirrors what dev_win.bat does:
    # Remove test/benchmark projects from solution, remove DirectXTex
    # reference, delete helper files that depend on DirectXTex.
    Write-Host "  Patching gta-toolkit (removing DirectXTex dependency)..."

    Push-Location $ToolkitDir
    try {
        # Remove projects that don't exist or aren't needed
        dotnet sln remove "Toolkit.Testing\Benchmarks\Benchmarks.csproj" 2>$null
        dotnet sln remove "Toolkit.Testing\Testing.RDR2\Testing.RDR2.csproj" 2>$null
        dotnet sln remove "Toolkit.Testing\Testing.GTA5\Testing.GTA5.csproj" 2>$null
        dotnet sln remove "_TestTools.GTA5\ExtractKeysFromDump\ExtractKeysFromDump.csproj" 2>$null
        dotnet sln remove "RageLib.GTA5.UnitTests\RageLib.GTA5.UnitTests.csproj" 2>$null
        dotnet sln remove "Libraries\DirectXTex\DirectXTex.vcxproj" 2>$null

        # Remove DirectXTex project reference from RageLib
        dotnet remove "RageLib\RageLib.csproj" reference "..\Libraries\DirectXTex\DirectXTex.vcxproj" 2>$null

        # Delete helper files that depend on DirectXTex
        $helpersToDelete = @(
            "RageLib\Helpers\DDSIO.cs",
            "RageLib\Helpers\TextureCompression.cs",
            "RageLib\Helpers\TextureConvert.cs"
        )
        foreach ($f in $helpersToDelete) {
            $fp = Join-Path $ToolkitDir $f
            if (Test-Path $fp) { Remove-Item $fp -Force }
        }

        # Create bin directory
        $BinDir = Join-Path $ToolkitDir "bin"
        if (Test-Path $BinDir) { Remove-Item -Recurse -Force $BinDir }
        New-Item -ItemType Directory -Path $BinDir | Out-Null

        # Publish RageLib.GTA5 (pulls in RageLib as dependency)
        Write-Host "  Building RageLib.GTA5..."
        dotnet publish "RageLib.GTA5\RageLib.GTA5.csproj" -c Release -r win-x64 --self-contained true --nologo
        if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed for RageLib.GTA5" }

        # Copy DLLs to bin/
        $RageLibDll = Get-ChildItem -Path "RageLib.GTA5" -Filter "RageLib.dll" -Recurse |
            Where-Object { $_.FullName -match "Release" } | Select-Object -First 1
        $RageLibGta5Dll = Get-ChildItem -Path "RageLib.GTA5" -Filter "RageLib.GTA5.dll" -Recurse |
            Where-Object { $_.FullName -match "Release" } | Select-Object -First 1
        if (-not $RageLibDll -or -not $RageLibGta5Dll) {
            throw "RageLib DLLs not found after publish."
        }
        Copy-Item $RageLibDll.FullName -Destination $BinDir
        Copy-Item $RageLibGta5Dll.FullName -Destination $BinDir
        Write-Host "  RageLib DLLs ready in bin/."
    } finally {
        Pop-Location
    }

    # -- Step B: Build FuckDX (DXT compressor, replaces DirectXTex) --
    Write-Host "  Building FuckDX..."

    # Download premake5
    $Premake5Url = "https://github.com/premake/premake-core/releases/download/v5.0.0-beta8/premake-5.0.0-beta8-windows.zip"
    $Premake5Zip = Join-Path $TempDir "premake5.zip"
    $Premake5Dir = Join-Path $TempDir "premake5"
    Invoke-WebRequest -Uri $Premake5Url -OutFile $Premake5Zip -UseBasicParsing
    Expand-Archive -Path $Premake5Zip -DestinationPath $Premake5Dir -Force
    $Premake5Exe = Join-Path $Premake5Dir "premake5.exe"
    if (-not (Test-Path $Premake5Exe)) {
        throw "premake5.exe not found in downloaded archive"
    }

    $FuckDxDir = Join-Path $YtdtoolRepo "fuckdx"
    Push-Location $FuckDxDir
    try {
        & $Premake5Exe vs2022
        if ($LASTEXITCODE -ne 0) {
            # Fall back to vs2019 if vs2022 not supported
            & $Premake5Exe vs2019
        }
        if ($LASTEXITCODE -ne 0) { throw "premake5 failed to generate project files" }

        $exitCode = Invoke-VsDev "msbuild FuckDX.sln -m -nologo -v:m -p:Configuration=Release"
        if ($exitCode -ne 0) { throw "MSBuild failed for FuckDX" }
    } finally {
        Pop-Location
    }

    # Copy FuckDX.dll to ytdtool bin
    $YtdBinDir = Join-Path $YtdtoolRepo "bin"
    if (-not (Test-Path $YtdBinDir)) { New-Item -ItemType Directory -Path $YtdBinDir | Out-Null }
    $FuckDxDll = Get-ChildItem -Path $FuckDxDir -Filter "FuckDX.dll" -Recurse |
        Where-Object { $_.FullName -match "Release" } | Select-Object -First 1
    if ($FuckDxDll) {
        Copy-Item $FuckDxDll.FullName -Destination $YtdBinDir
        Write-Host "  FuckDX.dll built."
    } else {
        Write-Warning "  FuckDX.dll not found - DXT compression may not work."
    }

    # -- Step C: Publish YTDToolio --
    Write-Host "  Publishing YTDToolio..."
    $YtdtoolioCsproj = Join-Path (Join-Path $YtdtoolRepo "ytdtoolio") "YTDToolio.csproj"
    dotnet publish $YtdtoolioCsproj -c Release -r win-x64 --self-contained true --nologo
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed for YTDToolio" }

    $PublishedExe = Get-ChildItem -Path (Join-Path $YtdtoolRepo "ytdtoolio") -Filter "YTDToolio.exe" -Recurse |
        Where-Object { $_.FullName -match "publish" } | Select-Object -First 1
    if (-not $PublishedExe) {
        throw "YTDToolio.exe not found after publish"
    }
    Copy-Item $PublishedExe.FullName -Destination $YtdtoolDest
    Write-Host "  Saved to $YtdtoolDest" -ForegroundColor Green
}

# ---------------------------------------------------------------------
#  Cleanup
# ---------------------------------------------------------------------
Write-Host "`nCleaning up temp files..." -ForegroundColor Cyan
if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }

# ---------------------------------------------------------------------
#  Summary
# ---------------------------------------------------------------------
Write-Host "`n=== Tools Summary ===" -ForegroundColor Green
$tools = @("gtautil.exe", "YTDToolio.exe")
$allPresent = $true
foreach ($tool in $tools) {
    $path = Join-Path $ToolsDir $tool
    if (Test-Path $path) {
        $size = (Get-Item $path).Length / 1KB
        Write-Host "  [OK] $tool ($([math]::Round($size, 0)) KB)" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $tool" -ForegroundColor Red
        $allPresent = $false
    }
}

if ($allPresent) {
    Write-Host "`nAll tools ready. You can now run: allin1 install" -ForegroundColor Green
} else {
    Write-Host "`nSome tools are missing. Check the errors above." -ForegroundColor Yellow
}
