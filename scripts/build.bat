@echo off
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo Once scripts\setup.bat calistirmalisin.
    pause
    exit /b 1
)

call scripts\clean.bat

echo [1/4] yt-dlp guncelleniyor (siteler sik degistigi icin)...
".venv\Scripts\python.exe" -m pip install -U "yt-dlp[default]"
if errorlevel 1 goto :fail

echo [2/4] Testler calistiriliyor...
".venv\Scripts\python.exe" -m pytest -q tests
if errorlevel 1 goto :fail

echo [3a/4] Web paketi uretiliyor (kucultme + karartma)...
".venv\Scripts\python.exe" scripts\build_web.py
if errorlevel 1 goto :fail

echo [3b/4] Kaynak kod karartiliyor (PyArmor)...
".venv\Scripts\python.exe" scripts\build_obfuscate.py
if errorlevel 1 goto :fail

echo [3c/4] PyInstaller ile EXE olusturuluyor...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist --workpath build\work build\getliyo.spec
if errorlevel 1 goto :fail

echo [4/4] Kurulum programi (Inno Setup) olusturuluyor...
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
if not defined ISCC (
    echo.
    echo [UYARI] Inno Setup bulunamadi, installer atlandi. EXE hazir: dist\getliyo.exe
    echo         Kurmak icin: winget install -e --id JRSoftware.InnoSetup  ^(sonra build.bat'i tekrar calistir^)
    pause
    exit /b 0
)
"%ISCC%" installer\getliyo.iss
if errorlevel 1 goto :fail

echo.
echo Bitti!
echo   EXE       : dist\getliyo.exe   (yaninda bin\ klasoru olmali)
echo   Installer : Output\getliyo-setup.exe
pause
exit /b 0

:fail
echo.
echo [HATA] Derleme basarisiz oldu. Yukaridaki mesaji oku.
pause
exit /b 1
