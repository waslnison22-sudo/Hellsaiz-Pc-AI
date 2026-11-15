@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1"
if errorlevel 1 (
    echo.
    echo Hellsaiz PC AI could not be started. Review the error above.
    pause
    exit /b 1
)
