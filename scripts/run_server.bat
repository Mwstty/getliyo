@echo off
setlocal
cd /d "%~dp0.."
REM Web sunucusunu tek tikla baslatir. Gerekirse once kurulumu (setup.bat) calistirir;
REM FFmpeg/Deno eksikse sunucu acilirken kendisi indirir.
if not exist ".venv\Scripts\python.exe" call scripts\setup.bat
if not exist ".venv\Scripts\python.exe" exit /b 1
start "" "http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m server
pause
