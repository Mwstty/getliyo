@echo off
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Once scripts\setup.bat calistirmalisin.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\register_extension.py %*
pause
