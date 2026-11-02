@echo off
cd /d "%~dp0.."
echo Eski derleme dosyalari temizleniyor...
if exist dist rmdir /s /q dist
if exist build\work rmdir /s /q build\work
if exist Output rmdir /s /q Output
if exist .pytest_cache rmdir /s /q .pytest_cache
for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
echo Temizlendi.
