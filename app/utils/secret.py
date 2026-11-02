"""Parola koruma (proxy şifresi vb.). Windows'ta DPAPI (CryptProtectData) — şifre yalnızca bu
Windows kullanıcı hesabında çözülebilir, düz metin olarak hiçbir yere yazılmaz.
Windows dışında güvenli saklama sağlayamadığımız için SAKLAMAZ (available() False)."""
from __future__ import annotations

import base64
import os

PREFIX = "dpapi:"


def available() -> bool:
    return os.name == "nt"


def protect(plain: str) -> str:
    if not plain:
        return ""
    if not available():
        return ""  # düz metin saklamaktansa hiç saklama
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    data = plain.encode("utf-8")
    buf = ctypes.create_string_buffer(data, len(data))
    inb = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    outb = Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(outb)):
        return ""
    try:
        raw = ctypes.string_at(outb.pbData, outb.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(outb.pbData)
    return PREFIX + base64.b64encode(raw).decode("ascii")


def unprotect(token: str) -> str:
    if not token or not token.startswith(PREFIX) or not available():
        return ""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    try:
        raw = base64.b64decode(token[len(PREFIX):])
    except ValueError:
        return ""
    buf = ctypes.create_string_buffer(raw, len(raw))
    inb = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    outb = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(outb)):
        return ""
    try:
        return ctypes.string_at(outb.pbData, outb.cbData).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(outb.pbData)


def redact_url(url: str) -> str:
    """Loglara yazılacak proxy URL'sinden kullanıcı adı/şifreyi çıkarır."""
    from urllib.parse import urlsplit

    p = urlsplit(url)
    host = p.hostname or ""
    if p.port:
        host += f":{p.port}"
    return f"{p.scheme}://{host}" if p.scheme else host
