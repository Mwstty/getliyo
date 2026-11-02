"""Dosya silme: Windows Geri Dönüşüm Kutusu'na gönderme ya da kalıcı silme (spec madde 18).

Windows'a özgü SHFileOperationW (FOF_ALLOWUNDO) kullanır — ekstra bağımlılık gerekmez.
Windows dışında (testler, geliştirme) kalıcı silmeye düşer.
"""
from __future__ import annotations

import os
from pathlib import Path

from app.utils.logger import get_logger

log = get_logger("trash")

FO_DELETE = 3
FOF_ALLOWUNDO = 0x40
FOF_NOCONFIRMATION = 0x10
FOF_NOERRORUI = 0x400
FOF_SILENT = 0x4


def send_to_recycle_bin(path: Path) -> bool:
    """Dosyayı Geri Dönüşüm Kutusu'na gönderir. Başarılıysa True."""
    if os.name != "nt":
        log.info("Windows dışında Geri Dönüşüm Kutusu desteklenmiyor, kalıcı siliniyor: %s", path)
        return permanently_delete(path)
    try:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        # pFrom çift NUL ile bitmeli (SHFileOperationW gereksinimi)
        from_buf = str(path) + "\0\0"
        op = SHFILEOPSTRUCTW(
            hwnd=None,
            wFunc=FO_DELETE,
            pFrom=from_buf,
            pTo=None,
            fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT,
        )
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if result != 0 or op.fAnyOperationsAborted:
            log.warning("SHFileOperationW basarisiz (kod %s), kalici silmeye dusuluyor: %s", result, path)
            return permanently_delete(path)
        return True
    except Exception:
        log.exception("Geri Dönüşüm Kutusu'na gönderilemedi: %s", path)
        return permanently_delete(path)


def permanently_delete(path: Path) -> bool:
    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            import shutil

            shutil.rmtree(path)
        return True
    except OSError:
        log.exception("Dosya kalici olarak silinemedi: %s", path)
        return False


def delete_file(path: Path, use_recycle_bin: bool = True) -> bool:
    """Ayar tercihine göre (Geri Dönüşüm Kutusu / kalıcı) dosyayı siler."""
    if not path.exists():
        return True  # zaten yok, "silindi" say
    return send_to_recycle_bin(path) if use_recycle_bin else permanently_delete(path)
