@echo off
setlocal DisableDelayedExpansion
title GTA V ALLIN1 - Uninstaller
color 0C

:: Change to script directory
cd /d "%~dp0"
setlocal EnableDelayedExpansion

:: Initialize log
set "LOGFILE=allin1.log"
echo. >> "%LOGFILE%"
echo [%date% %time%] uninstall.bat started >> "%LOGFILE%"

echo ============================================================
echo   GTA V ALLIN1 - Uninstaller
echo ============================================================
echo.
echo This will restore your original GTA V files from backup.
echo.

set /p CONFIRM="Are you sure you want to uninstall? (y/n): "
if /i not "!CONFIRM!"=="y" (
    echo Cancelled.
    echo [%date% %time%] Uninstall cancelled by user >> %LOGFILE%
    exit /b 0
)

:: Check venv exists
if not exist ".venv" (
    echo [ERROR] Virtual environment not found. Was ALLIN1 installed?
    echo [%date% %time%] ERROR: .venv not found >> %LOGFILE%
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

:: Use the venv executable directly so paths containing '&' are not re-parsed.
set "VENV_ALLIN1=.venv\Scripts\allin1.exe"
echo.
echo Restoring original game files...
echo.
echo [%date% %time%] Running allin1 uninstall... >> %LOGFILE%
"!VENV_ALLIN1!" uninstall

if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Uninstall failed. Check the error above.
    echo See allin1.log for details.
    echo [%date% %time%] ERROR: allin1 uninstall failed >> %LOGFILE%
    echo Press any key to exit...
    pause >nul
    exit /b 1
)

echo [%date% %time%] Uninstall completed successfully >> %LOGFILE%
echo.
echo ============================================================
echo   Uninstall complete! Original files have been restored.
echo   Full log saved to: allin1.log
echo ============================================================
echo.
