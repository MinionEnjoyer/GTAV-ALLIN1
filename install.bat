@echo off
setlocal enabledelayedexpansion
title GTA V ALLIN1 - Installer
color 0E

:: Change to script directory
cd /d "%~dp0"

:: Initialize log
set LOGFILE=allin1.log
echo. >> %LOGFILE%
echo ================================================================ >> %LOGFILE%
echo [%date% %time%] install.bat started >> %LOGFILE%
echo ================================================================ >> %LOGFILE%

echo ============================================================
echo   GTA V ALLIN1 - Unlock All GTA Online Vehicles in SP
echo ============================================================
echo.

:: Check for Python
echo [%date% %time%] Checking for Python... >> %LOGFILE%
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed or not in PATH.
        echo [%date% %time%] ERROR: Python not found in PATH >> %LOGFILE%
        echo.
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )
    set PYTHON=python3
) else (
    set PYTHON=python
)

:: Verify Python version
for /f "tokens=2 delims= " %%v in ('%PYTHON% --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)
if %PYMAJOR% lss 3 (
    echo [ERROR] Python 3.10+ is required. You have Python %PYVER%.
    echo [%date% %time%] ERROR: Python %PYVER% too old >> %LOGFILE%
    echo Press any key to exit...
    pause >nul
    exit /b 1
)
if %PYMAJOR% equ 3 if %PYMINOR% lss 10 (
    echo [ERROR] Python 3.10+ is required. You have Python %PYVER%.
    echo [%date% %time%] ERROR: Python %PYVER% too old >> %LOGFILE%
    echo Press any key to exit...
    pause >nul
    exit /b 1
)
echo [OK] Found Python %PYVER%
echo [%date% %time%] Found Python %PYVER% >> %LOGFILE%

:: Set up virtual environment if it doesn't exist
if not exist ".venv" (
    echo.
    echo Setting up virtual environment...
    echo [%date% %time%] Creating virtual environment... >> %LOGFILE%
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo [%date% %time%] ERROR: venv creation failed >> %LOGFILE%
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )
    echo [OK] Virtual environment created
    echo [%date% %time%] Virtual environment created >> %LOGFILE%
) else (
    echo [%date% %time%] Using existing virtual environment >> %LOGFILE%
)

:: Activate venv and install dependencies
echo.
echo Installing dependencies...
echo [%date% %time%] Installing dependencies... >> %LOGFILE%
call .venv\Scripts\activate.bat
echo [%date% %time%] Activated venv >> %LOGFILE%
pip install -e . --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies. See output above.
    echo [%date% %time%] ERROR: pip install failed >> %LOGFILE%
    echo Press any key to exit...
    pause >nul
    exit /b 1
)
echo [OK] Dependencies installed
echo [%date% %time%] Dependencies installed >> %LOGFILE%

:: Copy config if it doesn't exist
if not exist "config.toml" (
    echo.
    echo Creating config.toml from example...
    copy config.example.toml config.toml >nul
    echo [OK] Config created. Edit config.toml to customize settings.
    echo [%date% %time%] Created config.toml from example >> %LOGFILE%
) else (
    echo [OK] Using existing config.toml
    echo [%date% %time%] Using existing config.toml >> %LOGFILE%
)

:: Check for cached GTA path
if exist ".gta_path" (
    set /p CACHED_PATH=<.gta_path
    echo [OK] Using cached GTA V path: !CACHED_PATH!
    echo [%date% %time%] Found cached GTA V path: !CACHED_PATH! >> %LOGFILE%
)

:: Try installation (auto-detection + cache)
echo.
echo ============================================================
echo   Installing GTA Online vehicles into Single Player...
echo ============================================================
echo.
echo [%date% %time%] Running allin1 install... >> %LOGFILE%
allin1 install
if %errorlevel% neq 0 (
    echo.
    echo [INFO] Auto-detection could not find GTA V.
    echo [%date% %time%] Auto-detection failed, prompting for manual path >> %LOGFILE%
    echo.
    echo Please enter the full path to your GTA V installation folder.
    echo Example: D:\SteamLibrary\steamapps\common\Grand Theft Auto V
    echo.
    set /p GTA_PATH="GTA V path: "
    if "!GTA_PATH!"=="" (
        echo [ERROR] No path entered. Exiting.
        echo [%date% %time%] ERROR: No manual path entered >> %LOGFILE%
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )

    echo [%date% %time%] User entered path: !GTA_PATH! >> %LOGFILE%

    :: Write the path into config.toml and cache file
    echo.
    echo Updating config.toml with your GTA V path...
    %PYTHON% -c "import re; p=open('config.toml').read(); p=re.sub(r'gta_path\s*=\s*\"[^\"]*\"', 'gta_path = \"' + r'!GTA_PATH!'.replace('\\','\\\\') + '\"', p); open('config.toml','w').write(p)"
    echo !GTA_PATH!> .gta_path
    echo [%date% %time%] Wrote path to config.toml and .gta_path >> %LOGFILE%

    echo.
    echo ============================================================
    echo   Installing GTA Online vehicles into Single Player...
    echo ============================================================
    echo.
    echo [%date% %time%] Retrying allin1 install with manual path... >> %LOGFILE%
    allin1 install

    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Installation failed. Check the error above.
        echo Make sure the path you entered contains GTA5.exe.
        echo See allin1.log for details.
        echo [%date% %time%] ERROR: Installation failed after manual path entry >> %LOGFILE%
        echo.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )
)

echo [%date% %time%] Installation completed successfully >> %LOGFILE%
echo.
echo ============================================================
echo   Installation complete!
echo.
echo   To play:
echo     1. Run ALLIN1-Launcher.exe from your GTA V folder
echo     2. Launch GTA V normally (through Steam / Rockstar Launcher)
echo     3. The launcher detects the game and injects automatically
echo.
echo   Full log saved to: allin1.log
echo ============================================================
echo.
