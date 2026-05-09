@echo off
setlocal enabledelayedexpansion
title GTA V ALLIN1 - Updater
color 0B

:: Change to script directory
cd /d "%~dp0"

set LOGFILE=allin1.log
echo. >> %LOGFILE%
echo ================================================================ >> %LOGFILE%
echo [%date% %time%] update.bat started >> %LOGFILE%
echo ================================================================ >> %LOGFILE%

echo ============================================================
echo   GTA V ALLIN1 - Update from GitHub
echo ============================================================
echo.

:: Read GitHub token for private repo access
set GH_TOKEN=
if exist ".gh_token" (
    set /p GH_TOKEN=<.gh_token
)
if "!GH_TOKEN!"=="" (
    echo [ERROR] GitHub token not found.
    echo.
    echo This repo is private. You need a GitHub Personal Access Token.
    echo   1. Go to https://github.com/settings/tokens
    echo   2. Generate a token with "repo" scope
    echo   3. Save it to a file called .gh_token in this folder
    echo.
    echo Or paste your token now:
    set /p GH_TOKEN="Token: "
    if "!GH_TOKEN!"=="" (
        echo [ERROR] No token provided. Exiting.
        echo [%date% %time%] ERROR: No GitHub token >> %LOGFILE%
        pause >nul
        exit /b 1
    )
    echo !GH_TOKEN!> .gh_token
    echo [OK] Token saved to .gh_token
)
echo [%date% %time%] GitHub token loaded >> %LOGFILE%

:: Auth header for curl
set AUTH=-H "Authorization: token !GH_TOKEN!"

:: Read GTA V path from installer cache
set GTA_PATH=
if exist ".gta_path" (
    set /p GTA_PATH=<.gta_path
)

if "!GTA_PATH!"=="" (
    echo [ERROR] GTA V path not found. Run install.bat first.
    echo [%date% %time%] ERROR: .gta_path missing >> %LOGFILE%
    pause >nul
    exit /b 1
)

if not exist "!GTA_PATH!" (
    echo [ERROR] Cached path does not exist: !GTA_PATH!
    echo [%date% %time%] ERROR: Cached path invalid >> %LOGFILE%
    echo Run install.bat again to re-detect your GTA V location.
    pause >nul
    exit /b 1
)

set SCRIPTS_DIR=!GTA_PATH!\scripts
if not exist "!SCRIPTS_DIR!" (
    echo Creating scripts directory...
    mkdir "!SCRIPTS_DIR!"
)

echo [OK] GTA V path: !GTA_PATH!
echo.

:: GitHub API URLs for private repo (uses API to download raw content)
set REPO=MinionEnjoyer/GTAV-ALLIN1
set API_BASE=https://api.github.com/repos/%REPO%/contents
set RAW_BASE=https://raw.githubusercontent.com/%REPO%/main
set ZIP_URL=https://api.github.com/repos/%REPO%/zipball/main

:: Download ALLIN1.dll
echo Downloading ALLIN1.dll...
echo [%date% %time%] Downloading ALLIN1.dll >> %LOGFILE%
curl --fail -sL %AUTH% -H "Accept: application/vnd.github.raw+json" -o "!SCRIPTS_DIR!\ALLIN1.dll" "%API_BASE%/script/dist/ALLIN1.dll" 2>> %LOGFILE%
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download ALLIN1.dll
    echo         Check that your .gh_token is valid and has repo scope.
    echo [%date% %time%] ERROR: curl failed for ALLIN1.dll >> %LOGFILE%
    pause >nul
    exit /b 1
)
echo [OK] ALLIN1.dll updated

:: Download LemonUI.SHVDN3.dll
echo Downloading LemonUI.SHVDN3.dll...
echo [%date% %time%] Downloading LemonUI.SHVDN3.dll >> %LOGFILE%
curl --fail -sL %AUTH% -H "Accept: application/vnd.github.raw+json" -o "!SCRIPTS_DIR!\LemonUI.SHVDN3.dll" "%API_BASE%/script/dist/LemonUI.SHVDN3.dll" 2>> %LOGFILE%
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download LemonUI.SHVDN3.dll
    echo [%date% %time%] ERROR: curl failed for LemonUI.SHVDN3.dll >> %LOGFILE%
    pause >nul
    exit /b 1
)
echo [OK] LemonUI.SHVDN3.dll updated

:: Download vehicle preview images for GBAY browser
set PREVIEWS_DIR=!SCRIPTS_DIR!\previews
if not exist "!PREVIEWS_DIR!" mkdir "!PREVIEWS_DIR!"
echo Downloading vehicle preview images...
echo [%date% %time%] Downloading preview images >> %LOGFILE%
:: Download repo archive via authenticated API
curl --fail -sL %AUTH% -o "%TEMP%\allin1_repo.zip" "%ZIP_URL%" 2>> %LOGFILE%
if %errorlevel% neq 0 (
    echo [WARN] Failed to download preview images. Skipping.
    echo [%date% %time%] WARN: preview download failed >> %LOGFILE%
) else (
    echo Extracting preview images...
    powershell -Command "Expand-Archive -Force '%TEMP%\allin1_repo.zip' '%TEMP%\allin1_extract'" 2>> %LOGFILE%
    :: The zipball extracts to a folder like MinionEnjoyer-GTAV-ALLIN1-<sha>/
    for /d %%D in ("%TEMP%\allin1_extract\*") do set EXTRACT_DIR=%%D
    if exist "!EXTRACT_DIR!\script\dist\previews" (
        xcopy /s /y /q "!EXTRACT_DIR!\script\dist\previews\*" "!PREVIEWS_DIR!\" >nul 2>&1
        echo [OK] Preview images updated
        echo [%date% %time%] Preview images updated >> %LOGFILE%
    ) else (
        echo [WARN] Preview images not found in archive. Skipping.
        echo [%date% %time%] WARN: previews dir not found in archive >> %LOGFILE%
    )
    rd /s /q "%TEMP%\allin1_extract" >nul 2>&1
    del /q "%TEMP%\allin1_repo.zip" >nul 2>&1
)

:: Remove legacy ASI if present (traffic spawner is now in the DLL)
if exist "!GTA_PATH!\ALLIN1.asi" (
    del /q "!GTA_PATH!\ALLIN1.asi" >nul 2>&1
    echo [OK] Removed legacy ALLIN1.asi (no longer needed)
    echo [%date% %time%] Removed legacy ALLIN1.asi >> %LOGFILE%
)

:: Update config example (don't overwrite user config)
echo Downloading latest config.example.toml...
echo [%date% %time%] Downloading config.example.toml >> %LOGFILE%
curl --fail -sL %AUTH% -H "Accept: application/vnd.github.raw+json" -o "config.example.toml" "%API_BASE%/config.example.toml" 2>> %LOGFILE%
echo [OK] config.example.toml updated

:: Copy ALLIN1.toml to scripts dir if it exists locally
if exist "config.toml" (
    copy /y "config.toml" "!SCRIPTS_DIR!\ALLIN1.toml" >nul
    echo [OK] Config synced to scripts folder
)

echo.
echo [%date% %time%] Update completed successfully >> %LOGFILE%
echo ============================================================
echo   Update complete!
echo.
echo   Files updated:
echo     !SCRIPTS_DIR!\ALLIN1.dll
echo     !SCRIPTS_DIR!\LemonUI.SHVDN3.dll
echo.
echo   Launch GTA V to use the latest version.
echo ============================================================
echo.
pause
