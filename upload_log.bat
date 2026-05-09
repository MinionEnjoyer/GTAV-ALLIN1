@echo off
REM ================================================================
REM  upload_log.bat — Copy GBAY crash log from GTA V and push to git
REM
REM  Edit the two paths below to match your system, then double-click
REM  this file after a crash to upload the log.
REM ================================================================

REM --- Path to your GTA V root folder (where GTA5.exe lives) ---
set "GTA_PATH=D:\Programs\Steam\steamapps\common\Grand Theft Auto V Enhanced"

REM --- Path to your local clone of this repo ---
set "REPO_PATH=%~dp0"

REM ================================================================

set "LOG_SRC=%GTA_PATH%\scripts\ALLIN1_gbay.log"
set "SHVDN_SRC=%GTA_PATH%\ScriptHookVDotNet3.log"
set "LOG_DEST=%REPO_PATH%logs\ALLIN1_gbay.log"
set "SHVDN_DEST=%REPO_PATH%logs\ScriptHookVDotNet3.log"

echo.
echo Looking for logs...

if exist "%LOG_SRC%" (
    echo Found: %LOG_SRC%
    copy /Y "%LOG_SRC%" "%LOG_DEST%" >nul
    echo Copied GBAY log to repo.
) else (
    echo WARNING: %LOG_SRC% not found!
    echo The mod may not have written a log. Check if the DLL is deployed.
)

if exist "%SHVDN_SRC%" (
    echo Found: %SHVDN_SRC%
    copy /Y "%SHVDN_SRC%" "%SHVDN_DEST%" >nul
    echo Copied SHVDN log to repo.
) else (
    echo SHVDN log not found at %SHVDN_SRC%
)

echo.
echo Pushing to git...
cd /d "%REPO_PATH%"
git add logs\*.log
git commit -m "Upload crash logs"
git push

echo.
echo Done! Logs have been uploaded to the repo.
pause
