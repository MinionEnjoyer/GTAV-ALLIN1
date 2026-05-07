<#
.SYNOPSIS
    Downloads and builds the tools required by the ALLIN1 installer.

.DESCRIPTION
    Fetches gtautil.exe and builds YTDToolio.exe from source.
    All tools are placed in the tools/ directory.

    Prerequisites:
    - .NET 5.0+ SDK (for building YTDToolio)
    - MSBuild / Visual Studio Build Tools (for native DirectXTex dependency)
    - Internet connection
    - Git

.EXAMPLE
    .\runtools.ps1
#>

$ErrorActionPreference = "Stop"
$ScriptRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$ToolsDir = Join-Path $ScriptRoot "tools"

if (-not (Test-Path $ToolsDir)) {
    New-Item -ItemType Directory -Path $ToolsDir | Out-Null
}

$TempDir = Join-Path $ToolsDir "_build_temp"
if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# ─────────────────────────────────────────────────────────────────────
#  1. gtautil.exe  (indilo53/gtautil v2.2.7 — MIT license)
# ─────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────
#  2. YTDToolio.exe  (kngrektor/ytdtool — built from source)
#     Reads PNG files directly and packs them into .ytd archives.
#     Uses RageLib for DXT compression internally.
# ─────────────────────────────────────────────────────────────────────
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

    # Step 2a: Build gta-toolkit (RageLib + RageLib.GTA5)
    $ToolkitDir = Join-Path (Join-Path $YtdtoolRepo "vendor") "gta-toolkit"
    $ToolkitBinDir = Join-Path $ToolkitDir "bin"
    if (-not (Test-Path $ToolkitBinDir)) {
        New-Item -ItemType Directory -Path $ToolkitBinDir | Out-Null
    }

    Write-Host "  Building gta-toolkit (RageLib)..."

    # Locate MSBuild via vswhere (needed for native DirectXTex C++ project)
    $VsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    $MsBuildPath = $null

    if (Test-Path $VsWhere) {
        $VsInstall = & $VsWhere -latest -property installationPath 2>$null
        if ($VsInstall) {
            $MsBuildPath = Get-ChildItem -Path $VsInstall -Filter "MSBuild.exe" -Recurse |
                Where-Object { $_.FullName -match "Current" } |
                Select-Object -First 1
        }
    }

    # Build Toolkit.sln (includes RageLib + native DirectXTex)
    $ToolkitSln = Join-Path $ToolkitDir "Toolkit.sln"
    if ($MsBuildPath) {
        Write-Host "  Using MSBuild at: $($MsBuildPath.FullName)"
        & $MsBuildPath.FullName $ToolkitSln /p:Configuration=Release /m /nologo /v:m
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "  MSBuild failed. Trying dotnet build as fallback..."
            dotnet build $ToolkitSln -c Release --nologo
        }
    } else {
        Write-Host "  MSBuild not found, trying dotnet build..."
        dotnet build $ToolkitSln -c Release --nologo
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to build gta-toolkit. Install Visual Studio Build Tools with C++ workload."
    }

    # Copy built RageLib DLLs to the location YTDToolio expects
    $RageLibDll = Get-ChildItem -Path $ToolkitDir -Filter "RageLib.dll" -Recurse |
        Where-Object { $_.FullName -match "Release" } | Select-Object -First 1
    $RageLibGta5Dll = Get-ChildItem -Path $ToolkitDir -Filter "RageLib.GTA5.dll" -Recurse |
        Where-Object { $_.FullName -match "Release" } | Select-Object -First 1

    if (-not $RageLibDll -or -not $RageLibGta5Dll) {
        throw "RageLib DLLs not found after build. Ensure .NET 5+ SDK and VS Build Tools are installed."
    }

    Copy-Item $RageLibDll.FullName -Destination $ToolkitBinDir
    Copy-Item $RageLibGta5Dll.FullName -Destination $ToolkitBinDir

    # Copy native DirectXTexNet DLL if present
    $DirectXTexDll = Get-ChildItem -Path $ToolkitDir -Filter "DirectXTexNet*.dll" -Recurse |
        Where-Object { $_.FullName -match "Release" } | Select-Object -First 1
    if ($DirectXTexDll) {
        Copy-Item $DirectXTexDll.FullName -Destination $ToolkitBinDir
    }

    Write-Host "  RageLib DLLs ready."

    # Step 2b: Publish YTDToolio as self-contained exe
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

# ─────────────────────────────────────────────────────────────────────
#  Cleanup
# ─────────────────────────────────────────────────────────────────────
Write-Host "`nCleaning up temp files..." -ForegroundColor Cyan
if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }

# ─────────────────────────────────────────────────────────────────────
#  Summary
# ─────────────────────────────────────────────────────────────────────
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
