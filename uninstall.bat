@echo off
setlocal
title GTA V ALLIN1 - Uninstaller
color 0C

echo ============================================================
echo   GTA V ALLIN1 - Uninstaller
echo ============================================================
echo.
echo This will restore your original GTA V files from backup.
echo.

set /p CONFIRM="Are you sure you want to uninstall? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Cancelled.
    pause
    exit /b 0
)

:: Check venv exists
if not exist ".venv" (
    echo [ERROR] Virtual environment not found. Was ALLIN1 installed?
    pause
    exit /b 1
)

:: Activate and run uninstall
call .venv\Scripts\activate.bat
echo.
echo Restoring original game files...
echo.
allin1 uninstall

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Uninstall failed. Check the error above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Uninstall complete! Original files have been restored.
echo ============================================================
echo.
pause
