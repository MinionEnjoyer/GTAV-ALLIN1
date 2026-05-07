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

$GtautilDir = Join-Path $ToolsDir "gtautil"
$GtautilDest = Join-Path $GtautilDir "gtautil.exe"
if (Test-Path $GtautilDest) {
    Write-Host "  Already exists, skipping."
} else {
    $GtautilZipUrl = "https://github.com/indilo53/gtautil/releases/download/2.2.7/gtautil-2.2.7.zip"
    $GtautilZip = Join-Path $TempDir "gtautil.zip"
    $GtautilExtract = Join-Path $TempDir "gtautil_extract"

    Write-Host "  Downloading from $GtautilZipUrl"
    Invoke-WebRequest -Uri $GtautilZipUrl -OutFile $GtautilZip -UseBasicParsing

    Write-Host "  Extracting..."
    Expand-Archive -Path $GtautilZip -DestinationPath $GtautilExtract -Force

    # Copy entire extracted folder contents into tools/gtautil/
    # gtautil needs its dependency DLLs alongside the exe
    if (-not (Test-Path $GtautilDir)) { New-Item -ItemType Directory -Path $GtautilDir | Out-Null }
    $GtautilExe = Get-ChildItem -Path $GtautilExtract -Filter "gtautil.exe" -Recurse | Select-Object -First 1
    if (-not $GtautilExe) {
        throw "gtautil.exe not found in downloaded archive"
    }
    # Copy all files from the folder containing gtautil.exe
    Copy-Item (Join-Path $GtautilExe.DirectoryName "*") -Destination $GtautilDir -Recurse -Force
    Write-Host "  Saved to $GtautilDir" -ForegroundColor Green
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

    # -- Locate Visual Studio and ensure C++ workload is installed --
    $VsWhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $VsWhere)) {
        throw "vswhere.exe not found. Install Visual Studio 2022."
    }
    $VsInstall = & $VsWhere -latest -property installationPath 2>$null
    if (-not $VsInstall) { throw "No Visual Studio installation found." }

    # Check if C++ desktop workload is installed
    $HasCpp = & $VsWhere -latest -requires Microsoft.VisualStudio.Workload.NativeDesktop -property installationPath 2>$null
    if (-not $HasCpp) {
        Write-Host "  C++ desktop workload not found. Installing..." -ForegroundColor Yellow
        $VsInstaller = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vs_installer.exe"
        if (-not (Test-Path $VsInstaller)) {
            throw "VS Installer not found. Open Visual Studio Installer and add 'Desktop development with C++' manually."
        }
        # Install the C++ workload silently
        $installArgs = @(
            "modify",
            "--installPath", $VsInstall,
            "--add", "Microsoft.VisualStudio.Workload.NativeDesktop",
            "--includeRecommended",
            "--passive",
            "--norestart"
        )
        Write-Host "  Running VS Installer (this may take a few minutes)..."
        $proc = Start-Process -FilePath $VsInstaller -ArgumentList $installArgs -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            throw "VS Installer failed (exit code $($proc.ExitCode)). Open Visual Studio Installer and add 'Desktop development with C++' manually."
        }
        Write-Host "  C++ workload installed." -ForegroundColor Green
    }

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

    # -- Step B: Build FuckDX.dll (required DXT compressor for YTDToolio) --
    # Compile directly with cl.exe instead of premake5 + MSBuild.
    # FuckDX is a single C++ source file that builds into a DLL.
    Write-Host "  Building FuckDX.dll..."

    $FuckDxDir = Join-Path $YtdtoolRepo "fuckdx"
    $FuckDxOut = Join-Path $TempDir "fuckdx_build"
    if (-not (Test-Path $FuckDxOut)) { New-Item -ItemType Directory -Path $FuckDxOut | Out-Null }

    $FuckDxSrc = Join-Path $FuckDxDir "main.cpp"
    $FuckDxDll = Join-Path $FuckDxOut "FuckDX.dll"

    # Compile with cl.exe via VS developer environment
    $clCmd = "cd /d `"$FuckDxOut`" && cl /nologo /O2 /std:c++17 /LD /EHsc /I`"$FuckDxDir`" `"$FuckDxSrc`" /Fe:`"$FuckDxDll`" /link /DLL"
    $exitCode = Invoke-VsDev $clCmd
    if ($exitCode -ne 0) {
        throw "Failed to compile FuckDX.dll. Ensure VS 2022 C++ desktop workload is installed."
    }
    if (-not (Test-Path $FuckDxDll)) {
        throw "FuckDX.dll was not created after compilation."
    }

    # Copy FuckDX.dll next to YTDToolio.exe (it loads it at runtime)
    Copy-Item $FuckDxDll -Destination $ToolsDir -Force
    Write-Host "  FuckDX.dll built and placed in tools/." -ForegroundColor Green

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
$toolPaths = @{
    "gtautil.exe" = Join-Path (Join-Path $ToolsDir "gtautil") "gtautil.exe"
    "YTDToolio.exe" = Join-Path $ToolsDir "YTDToolio.exe"
    "FuckDX.dll" = Join-Path $ToolsDir "FuckDX.dll"
}
$allPresent = $true
foreach ($entry in $toolPaths.GetEnumerator()) {
    if (Test-Path $entry.Value) {
        $size = (Get-Item $entry.Value).Length / 1KB
        Write-Host "  [OK] $($entry.Key) ($([math]::Round($size, 0)) KB)" -ForegroundColor Green
    } else {
        Write-Host "  [MISSING] $($entry.Key)" -ForegroundColor Red
        $allPresent = $false
    }
}

if ($allPresent) {
    Write-Host "`nAll tools ready. You can now run: allin1 install" -ForegroundColor Green
} else {
    Write-Host "`nSome tools are missing. Check the errors above." -ForegroundColor Yellow
}
