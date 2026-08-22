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

:: Find a real Python 3.10+ installation. This rejects the Microsoft Store
:: execution alias and also supports Python's standard Windows `py` launcher.
echo [%date% %time%] Checking for Python 3.10 or newer... >> %LOGFILE%
call :find_python
if /i "%~1"=="--check-python" (
    if not defined PYTHON_EXE (
        echo [ERROR] Python 3.10 or newer was not found.
        exit /b 1
    )
    echo [OK] Compatible Python found at !PYTHON_EXE!
    "!PYTHON_EXE!" --version
    exit /b 0
)
if not defined PYTHON_EXE (
    echo [INFO] Python 3.10 or newer is required but was not found.
    echo [%date% %time%] Compatible Python not found; starting winget install >> %LOGFILE%
    echo.

    where winget.exe >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Windows Package Manager is not available.
        echo Install Python from https://www.python.org/downloads/windows/
        echo Select "Add Python to PATH", then run install.bat again.
        echo [%date% %time%] ERROR: winget is unavailable >> %LOGFILE%
        echo.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )

    echo Installing 64-bit Python 3.12 for this Windows account...
    echo This may take a few minutes.
    echo.
    winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo [ERROR] Python could not be installed automatically.
        echo Install it from https://www.python.org/downloads/windows/
        echo and then run install.bat again.
        echo [%date% %time%] ERROR: winget Python installation failed >> %LOGFILE%
        echo.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )

    call :find_python
    if not defined PYTHON_EXE (
        echo.
        echo [ERROR] Python was installed, but Windows has not exposed it yet.
        echo Close this window and run install.bat again.
        echo [%date% %time%] ERROR: Python unavailable after winget installation >> %LOGFILE%
        echo.
        echo Press any key to exit...
        pause >nul
        exit /b 1
    )
)

for /f "delims=" %%v in ('"!PYTHON_EXE!" -c "import platform; print(platform.python_version())" 2^>nul') do set "PYVER=%%v"
echo [OK] Found Python !PYVER!
echo [%date% %time%] Found Python !PYVER! at !PYTHON_EXE! >> %LOGFILE%

:: Set up virtual environment if it doesn't exist
if not exist ".venv" (
    echo.
    echo Setting up virtual environment...
    echo [%date% %time%] Creating virtual environment... >> %LOGFILE%
    "!PYTHON_EXE!" -m venv .venv
    if errorlevel 1 (
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
".venv\Scripts\python.exe" -m pip install -e . --quiet
if errorlevel 1 (
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
if errorlevel 1 (
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
    "!PYTHON_EXE!" -c "import re; p=open('config.toml').read(); p=re.sub(r'gta_path\s*=\s*\"[^\"]*\"', 'gta_path = \"' + r'!GTA_PATH!'.replace('\\','\\\\') + '\"', p); open('config.toml','w').write(p)"
    echo !GTA_PATH!> .gta_path
    echo [%date% %time%] Wrote path to config.toml and .gta_path >> %LOGFILE%

    echo.
    echo ============================================================
    echo   Installing GTA Online vehicles into Single Player...
    echo ============================================================
    echo.
    echo [%date% %time%] Retrying allin1 install with manual path... >> %LOGFILE%
    allin1 install

    if errorlevel 1 (
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
echo   To play: launch GTA V normally.
echo   DLC vehicles will appear in traffic while you drive.
echo.
echo   Requires:
echo     ScriptHookV:              http://www.dev-c.com/gtav/scripthookv/
echo     ScriptHookVDotNet Enhanced: github.com/Chiheb-Bacha/scripthookvdotnetenhanced
echo.
echo   Full log saved to: allin1.log
echo ============================================================
echo.
exit /b 0

:: Set PYTHON_EXE when a genuine Python 3.10+ runtime is available. Calling
:: Python itself avoids treating the Microsoft Store alias as an installation.
:find_python
set "PYTHON_EXE="
call :try_python ".venv\Scripts\python.exe"
if defined PYTHON_EXE exit /b 0
call :try_python "python.exe"
if defined PYTHON_EXE exit /b 0
call :try_python "python3.exe"
if defined PYTHON_EXE exit /b 0

where py.exe >nul 2>&1
if errorlevel 1 goto :try_python_default
set "PYTHON_FROM_LAUNCHER="
for /f "delims=" %%p in ('py.exe -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_FROM_LAUNCHER=%%p"
if defined PYTHON_FROM_LAUNCHER call :try_python "!PYTHON_FROM_LAUNCHER!"
if defined PYTHON_EXE exit /b 0

:try_python_default
call :try_python "%LocalAppData%\Programs\Python\Python312\python.exe"
exit /b 0

:try_python
set "PYTHON_CANDIDATE=%~1"
"!PYTHON_CANDIDATE!" -c "import sys; ok = (sys.version_info.major == 3 and sys.version_info.minor in range(10, 100)) or sys.version_info.major in range(4, 100); raise SystemExit(0 if ok else 1)" >nul 2>&1
if not errorlevel 1 set "PYTHON_EXE=!PYTHON_CANDIDATE!"
set "PYTHON_CANDIDATE="
exit /b 0
