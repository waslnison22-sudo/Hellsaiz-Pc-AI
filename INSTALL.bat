@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
if errorlevel 1 (
    echo.
    echo Hellsaiz PC AI installation failed. Review the error above.
    pause
    exit /b 1
)
echo.
echo Setup completed. Start the application with RUN.bat.
pause
