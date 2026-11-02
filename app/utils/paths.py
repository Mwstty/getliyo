"""Yol yardımcıları: kaynak dosyaları, ayar/log klasörleri, varsayılan indirme klasörü."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "getliyo"
LEGACY_APP_NAME = "MIT Dosya İndirici"  # eski sürümün veri klasörü (otomatik taşınır)


def is_frozen() -> bool:
    """PyInstaller ile paketlenmiş EXE olarak mı çalışıyoruz?"""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def app_dir() -> Path:
    """EXE'nin (veya geliştirme sırasında proje kökünün) bulunduğu klasör."""
    return Path(sys.executable).resolve().parent if is_frozen() else project_root()


def resource_path(relative: str) -> Path:
    """Pakete gömülü kaynak dosyasının yolu (icon, config vb.)."""
    base = Path(getattr(sys, "_MEIPASS", project_root()))
    return base / relative


PORTABLE_MARKER = "portable.flag"


def is_portable() -> bool:
    """EXE'nin yanında 'portable.flag' varsa uygulama verilerini kendi klasöründe tutar (spec 55)."""
    return (app_dir() / PORTABLE_MARKER).is_file()


def appdata_dir() -> Path:
    """Kullanıcı verisi (ayar, geçmiş, log, cache). Kurulu sürümde %APPDATA%\\getliyo
    (Program Files'a ASLA yazılmaz); portable modda EXE'nin yanındaki data\\ klasörü."""
    if is_portable():
        path = app_dir() / "data"
    else:
        root = os.environ.get("APPDATA") or str(Path.home() / ".config")
        path = Path(root) / APP_NAME
        legacy = Path(root) / LEGACY_APP_NAME
        if not path.exists() and legacy.is_dir():
            try:
                legacy.rename(path)  # eski ad altındaki ayar/geçmiş kaybolmasın
            except OSError:
                pass
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = appdata_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return appdata_dir() / "settings.json"


def log_dir() -> Path:
    path = appdata_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_download_dir() -> Path:
    home = os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / "Downloads" / APP_NAME
