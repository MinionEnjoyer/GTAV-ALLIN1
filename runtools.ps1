<#
.SYNOPSIS
    Downloads and builds the tools required by the ALLIN1 installer.

.DESCRIPTION
    Fetches gtautil.exe and builds YTDToolio.exe from source.
    All tools are placed in the tools/ directory.

    Prerequisites:
    - .NET SDK (for building YTDToolio)
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

    # Build only the projects we need — skip the full Toolkit.sln which
    # references missing test/benchmark projects and requires native C++ builds.
    $ToolkitDir = Join-Path (Join-Path $YtdtoolRepo "vendor") "gta-toolkit"

    # Build RageLib (core library)
    $RageLibProj = Join-Path (Join-Path $ToolkitDir "RageLib") "RageLib.csproj"
    Write-Host "  Restoring & building RageLib..."
    dotnet restore $RageLibProj --nologo
    if ($LASTEXITCODE -ne 0) { throw "dotnet restore failed for RageLib" }
    dotnet build $RageLibProj -c Release --nologo --no-restore
    if ($LASTEXITCODE -ne 0) { throw "dotnet build failed for RageLib" }

    # Build RageLib.GTA5 (GTA V specific library)
    $RageLibGta5Proj = Join-Path (Join-Path $ToolkitDir "RageLib.GTA5") "RageLib.GTA5.csproj"
    Write-Host "  Restoring & building RageLib.GTA5..."
    dotnet restore $RageLibGta5Proj --nologo
    if ($LASTEXITCODE -ne 0) { throw "dotnet restore failed for RageLib.GTA5" }
    dotnet build $RageLibGta5Proj -c Release --nologo --no-restore
    if ($LASTEXITCODE -ne 0) { throw "dotnet build failed for RageLib.GTA5" }

    Write-Host "  RageLib projects built."

    # Publish YTDToolio as self-contained exe
    Write-Host "  Publishing YTDToolio..."
    $YtdtoolioCsproj = Join-Path (Join-Path $YtdtoolRepo "ytdtoolio") "YTDToolio.csproj"
    dotnet restore $YtdtoolioCsproj --nologo
    if ($LASTEXITCODE -ne 0) { throw "dotnet restore failed for YTDToolio" }
    dotnet publish $YtdtoolioCsproj -c Release -r win-x64 --self-contained true --nologo --no-restore
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
