@echo off
setlocal
cd /d "%~dp0.."
echo ============================================
echo  getliyo - Gelistirme ortami kurulumu
echo ============================================

set "PY="
py -3.12 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3.12"
if not defined PY (
    python --version 2>nul | findstr /b /c:"Python 3.12" >nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo.
    echo [HATA] Python 3.12 bulunamadi.
    echo  1^) Komut istemine su komutu yaz:  winget install -e --id Python.Python.3.12
    echo     ^(ya da https://www.python.org/downloads/ adresinden 3.12 indir;
    echo      kurarken "Add python.exe to PATH" kutusunu isaretle^)
    echo  2^) Kurulum bitince bu pencereyi kapat ve setup.bat'i tekrar calistir.
    pause
    exit /b 1
)

echo [1/5] Sanal ortam olusturuluyor (.venv)...
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if errorlevel 1 goto :fail

echo [2/5] pip kontrol ediliyor...
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 goto :repair_pip
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 goto :repair_pip
goto :after_pip

:repair_pip
REM pip kendi kendini guncellerken bozulmus olabilir (ozellikle OneDrive/Downloads gibi
REM senkronize klasorlerde dosya kilitlenmesi yuzunden). ensurepip, Python'la birlikte gelen
REM temiz pip kopyasini geri yukler; internet gerektirmez.
echo   pip bozulmus, onariliyor...
".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>nul
".venv\Scripts\python.exe" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo [HATA] pip onarilamadi.
    echo  En kesin cozum: bu klasoru OneDrive/Downloads disinda, bossuz bir yola tasi
    echo  ^(ornek: C:\getliyo^), ".venv" klasorunu sil, setup.bat'i tekrar calistir.
    pause
    exit /b 1
)
:after_pip

echo [3/5] Bagimliliklar kuruluyor (birkac dakika surebilir)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [4/5] FFmpeg ve Deno indiriliyor (bin\ klasorune)...
".venv\Scripts\python.exe" scripts\fetch_ffmpeg.py
if errorlevel 1 goto :fail

echo [5/5] Ikonlar kontrol ediliyor...
if not exist "resources\icon.ico" ".venv\Scripts\python.exe" scripts\make_icons.py

echo.
echo Kurulum tamam! Uygulamayi calistirmak icin: scripts\run.bat
pause
exit /b 0

:fail
echo.
echo [HATA] Kurulum basarisiz oldu. Yukaridaki mesaji oku, internetini kontrol et ve tekrar dene.
pause
exit /b 1
