# -*- mode: python ; coding: utf-8 -*-
# PyInstaller tanımı. Kullanım: scripts\build.bat  (SPECPATH = bu dosyanın klasörü)
# Kaynak olarak build/obfuscated/ (scripts/build_obfuscate.py üretir — PyArmor ile
# karartılmış app/ ve server/) kullanılır, ham kaynak değil.
import os
import glob

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
OBF = os.path.join(ROOT, "build", "obfuscated")
if not os.path.isdir(os.path.join(OBF, "app")):
    raise SystemExit("build/obfuscated/app yok — önce scripts\\build_obfuscate.py çalıştır.")

runtime_dirs = [os.path.basename(p) for p in glob.glob(os.path.join(OBF, "pyarmor_runtime_*"))]
if not runtime_dirs:
    raise SystemExit("build/obfuscated altında pyarmor_runtime_* yok — karartma eksik üretilmiş.")

# Üretim web paketi varsa (küçültülmüş/karartılmış) onu, yoksa kaynağı kullan.
web_dir = os.path.join(ROOT, "server", "web-dist")
if not os.path.isdir(web_dir):
    web_dir = os.path.join(ROOT, "server", "web")

hiddenimports = collect_submodules("yt_dlp")
try:
    hiddenimports += collect_submodules("yt_dlp_ejs")
except Exception:
    pass
# Gömülü yerel web sunucusu (server/ paketi, uvicorn protokol/döngü modülleri dinamik yüklenir)
for pkg in ("uvicorn", "server"):
    hiddenimports += collect_submodules(pkg)
hiddenimports += runtime_dirs  # pyarmor çalışma zamanı (.pyd) — otomatik keşfedilemez
datas = [
    (web_dir, os.path.join("server", "web")),
    (os.path.join(ROOT, "config"), "config"),
    (os.path.join(ROOT, "resources"), "resources"),
]
for pkg in ("yt_dlp_ejs", "certifi"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

a = Analysis(
    [os.path.join(OBF, "app", "main.py")],
    pathex=[OBF],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="getliyo",
    icon=os.path.join(ROOT, "resources", "icon.ico"),
    console=False,
    upx=False,
)

# --- Native Messaging host: tarayıcı eklentisinin çağırdığı ayrı, hafif EXE ---
# PySide6/yt-dlp'yi içermez (yalnızca stdlib) -> Chrome'un beklediği hızda açılır.
host_a = Analysis(
    [os.path.join(OBF, "app", "native_host.py")],
    pathex=[OBF],
    datas=[],
    hiddenimports=runtime_dirs,
    excludes=["tkinter"],
    noarchive=False,
)
host_pyz = PYZ(host_a.pure)
host_exe = EXE(
    host_pyz,
    host_a.scripts,
    host_a.binaries,
    host_a.datas,
    [],
    name="getliyo-host",
    icon=os.path.join(ROOT, "resources", "icon.ico"),
    console=False,
    upx=False,
)

# --- Eklenti kayıt aracı: kurulu uygulamanın yanına konur, çift tıkla çalışır ---
# winreg dışında bağımlılığı yok (stdlib) -> hızlı açılır. Konsol penceresi açık kalır
# ki kullanıcı Extension ID'yi yapıştırıp Enter'a basabilsin (console=True).
reg_a = Analysis(
    [os.path.join(ROOT, "scripts", "register_extension.py")],
    pathex=[ROOT],
    datas=[],
    hiddenimports=[],
    excludes=["tkinter"],
    noarchive=False,
)
reg_pyz = PYZ(reg_a.pure)
reg_exe = EXE(
    reg_pyz,
    reg_a.scripts,
    reg_a.binaries,
    reg_a.datas,
    [],
    name="getliyo-eklenti-kayit",
    icon=os.path.join(ROOT, "resources", "icon.ico"),
    console=True,
    upx=False,
)
