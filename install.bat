@echo off
setlocal enabledelayedexpansion
title GTA V ALLIN1 - Installer
color 0E

echo ============================================================
echo   GTA V ALLIN1 - Unlock All GTA Online Vehicles in SP
echo ============================================================
echo.

:: Check for Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    where python3 >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed or not in PATH.
        echo.
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
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
    pause
    exit /b 1
)
if %PYMAJOR% equ 3 if %PYMINOR% lss 10 (
    echo [ERROR] Python 3.10+ is required. You have Python %PYVER%.
    pause
    exit /b 1
)
echo [OK] Found Python %PYVER%

:: Set up virtual environment if it doesn't exist
if not exist ".venv" (
    echo.
    echo Setting up virtual environment...
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

:: Activate venv and install dependencies
echo.
echo Installing dependencies...
call .venv\Scripts\activate.bat
pip install -e . --quiet 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed

:: Copy config if it doesn't exist
if not exist "config.toml" (
    echo.
    echo Creating config.toml from example...
    copy config.example.toml config.toml >nul
    echo [OK] Config created. Edit config.toml to customize settings.
) else (
    echo [OK] Using existing config.toml
)

:: Try auto-detection first, prompt for path if it fails
echo.
echo Searching for GTA V installation...
allin1 install
if %errorlevel% neq 0 (
    echo.
    echo [INFO] Auto-detection could not find GTA V.
    echo.
    echo Please enter the full path to your GTA V installation folder.
    echo Example: D:\SteamLibrary\steamapps\common\Grand Theft Auto V
    echo.
    set /p GTA_PATH="GTA V path: "
    if "!GTA_PATH!"=="" (
        echo [ERROR] No path entered. Exiting.
        pause
        exit /b 1
    )

    :: Write the path into config.toml
    echo.
    echo Updating config.toml with your GTA V path...
    %PYTHON% -c "import re; p=open('config.toml').read(); p=re.sub(r'gta_path\s*=\s*\"[^\"]*\"', 'gta_path = \"' + r'!GTA_PATH!'.replace('\\','\\\\') + '\"', p); open('config.toml','w').write(p)"

    echo.
    echo ============================================================
    echo   Installing GTA Online vehicles into Single Player...
    echo ============================================================
    echo.
    allin1 install

    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Installation failed. Check the error above.
        echo Make sure the path you entered contains GTA5.exe.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo   Installation complete!
echo.
echo   Prerequisites (if not already installed):
echo   - ASI Loader (dinput8.dll) in your GTA V folder
echo   - OpenIV.asi (or OpenRPF for Enhanced Edition)
echo.
echo   These redirect the game to read from the mods/ folder.
echo   Download OpenIV from openiv.com if you haven't already.
echo ============================================================
echo.
pause
