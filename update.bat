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

:: Resolve GTA V path
set GTA_PATH=
if exist ".gta_path" (
    set /p GTA_PATH=<.gta_path
)

if "!GTA_PATH!"=="" (
    echo [INFO] No cached GTA V path found.
    echo Please enter the full path to your GTA V installation folder.
    echo Example: D:\SteamLibrary\steamapps\common\Grand Theft Auto V
    echo.
    set /p GTA_PATH="GTA V path: "
    if "!GTA_PATH!"=="" (
        echo [ERROR] No path entered. Exiting.
        echo [%date% %time%] ERROR: No GTA path >> %LOGFILE%
        pause >nul
        exit /b 1
    )
    echo !GTA_PATH!> .gta_path
    echo [%date% %time%] Saved GTA path: !GTA_PATH! >> %LOGFILE%
)

:: Verify GTA path exists
if not exist "!GTA_PATH!\GTA5.exe" (
    echo [ERROR] GTA5.exe not found at: !GTA_PATH!
    echo [%date% %time%] ERROR: GTA5.exe not found at !GTA_PATH! >> %LOGFILE%
    echo.
    echo Please check the path and try again.
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

:: GitHub raw URLs (main branch, CI-built binaries)
set BASE_URL=https://raw.githubusercontent.com/MinionEnjoyer/GTAV-ALLIN1/main
set DLL_URL=%BASE_URL%/script/dist/ALLIN1.dll
set LEMON_URL=%BASE_URL%/script/dist/LemonUI.SHVDN3.dll
set ASI_URL=%BASE_URL%/asi/dist/ALLIN1.asi
set CONFIG_URL=%BASE_URL%/config.example.toml

:: Download ALLIN1.dll
echo Downloading ALLIN1.dll...
echo [%date% %time%] Downloading ALLIN1.dll >> %LOGFILE%
curl -sL -o "!SCRIPTS_DIR!\ALLIN1.dll" "%DLL_URL%"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download ALLIN1.dll
    echo [%date% %time%] ERROR: curl failed for ALLIN1.dll >> %LOGFILE%
    pause >nul
    exit /b 1
)
echo [OK] ALLIN1.dll updated

:: Download LemonUI.SHVDN3.dll
echo Downloading LemonUI.SHVDN3.dll...
echo [%date% %time%] Downloading LemonUI.SHVDN3.dll >> %LOGFILE%
curl -sL -o "!SCRIPTS_DIR!\LemonUI.SHVDN3.dll" "%LEMON_URL%"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download LemonUI.SHVDN3.dll
    echo [%date% %time%] ERROR: curl failed for LemonUI.SHVDN3.dll >> %LOGFILE%
    pause >nul
    exit /b 1
)
echo [OK] LemonUI.SHVDN3.dll updated

:: Download ALLIN1.asi
echo Downloading ALLIN1.asi...
echo [%date% %time%] Downloading ALLIN1.asi >> %LOGFILE%
curl -sL -o "!GTA_PATH!\ALLIN1.asi" "%ASI_URL%"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to download ALLIN1.asi
    echo [%date% %time%] ERROR: curl failed for ALLIN1.asi >> %LOGFILE%
    pause >nul
    exit /b 1
)
echo [OK] ALLIN1.asi updated

:: Update config example (don't overwrite user config)
echo Downloading latest config.example.toml...
echo [%date% %time%] Downloading config.example.toml >> %LOGFILE%
curl -sL -o "config.example.toml" "%CONFIG_URL%"
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
echo     !GTA_PATH!\ALLIN1.asi
echo.
echo   Launch GTA V to use the latest version.
echo ============================================================
echo.
pause
