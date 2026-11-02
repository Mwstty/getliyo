"""Metinden URL çıkarma (toplu giriş, sürükle-bırak, pano) ve desteklenen-URL algılama."""
from __future__ import annotations

import re
from typing import Optional

from app.downloaders.platform_detector import OTHER_NAME, detect_platform
from app.utils.validators import is_valid_url

_URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
_TRAILING = ".,;:!?)]}>'\""
MAX_CLIPBOARD_CHARS = 2000  # şifre yöneticisi/uzun metin gibi alakasız panoları işleme


def parse_urls(text: str) -> list[str]:
    """Metindeki tüm geçerli http(s) URL'leri sırayla, tekrarsız döndürür."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _URL_RE.findall(text or ""):
        url = match.rstrip(_TRAILING)
        if url and url not in seen and is_valid_url(url):
            seen.add(url)
            out.append(url)
    return out


def is_supported_url(url: str) -> bool:
    """Bilinen platform ya da doğrudan medya bağlantısı mı? ('Diğer web sitesi' desteklenmiş SAYILMAZ)."""
    if not is_valid_url(url):
        return False
    info = detect_platform(url)
    return info.name != OTHER_NAME or info.is_direct_media


def clipboard_candidate(text: str) -> Optional[str]:
    """Panodaki metin TEK BAŞINA bir desteklenen bağlantıysa onu döndürür (spec madde 24, 67).
    Uzun/çok satırlı/karışık metinler (ör. şifre yöneticisi çıktısı) yok sayılır."""
    text = (text or "").strip()
    if not text or len(text) > MAX_CLIPBOARD_CHARS or text.count("\n") > 0:
        return None
    if not text.lower().startswith(("http://", "https://")):
        return None
    urls = parse_urls(text)
    if len(urls) != 1 or urls[0] != text.rstrip(_TRAILING):
        return None
    return urls[0] if is_supported_url(urls[0]) else None
