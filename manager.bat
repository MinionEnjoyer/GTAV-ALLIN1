@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\allin1-gui.exe" (
    echo GTA V ALLIN1 is not installed yet.
    echo Run install.bat first, then open manager.bat again.
    pause
    exit /b 1
)

start "GTA V ALLIN1 Manager" ".venv\Scripts\allin1-gui.exe"
