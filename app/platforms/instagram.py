"""Instagram: yt-dlp'nin bulamadığı (fotoğraf/albüm) gönderiler için herkese açık embed sayfası taraması.

yt-dlp Instagram'da çoğunlukla sadece video/reel indirir; fotoğraf ve albüm gönderilerinde
"There is no video in this post" der. Herkese açık gönderilerin /embed/captioned/ sayfası
giriş gerektirmeden medya adreslerini içerir, buradan (kind, url) listesi çıkarılır.
Özel hesaplar ve giriş isteyen gönderiler için tarayıcı çerezi (Ayarlar) gerekir.
"""
from __future__ import annotations

import html
import re
from typing import Optional
from urllib.parse import urlsplit

_SHORTCODE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:[^/?#]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)
_DISPLAY = re.compile(r'"display_url"\s*:\s*"([^"]+)"')
_VIDEO = re.compile(r'"video_url"\s*:\s*"([^"]+)"')
_IMG_TAG = re.compile(r'<img[^>]+class="[^"]*EmbeddedMediaImage[^"]*"[^>]*\ssrc="([^"]+)"', re.IGNORECASE)


def shortcode(url: str) -> Optional[str]:
    match = _SHORTCODE.match(url.strip())
    return match.group(1) if match else None


def embed_url(code: str) -> str:
    return f"https://www.instagram.com/p/{code}/embed/captioned/"


def _clean(raw: str) -> str:
    text = re.sub(r"\\+/", "/", raw)  # \/ veya \\/ -> /
    text = re.sub(r"\\+u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)  # \u0026 -> &
    return html.unescape(text).strip()


def _normalize(page: str) -> str:
    return page.replace('\\\\"', '"').replace('\\"', '"')


def _dedupe(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not u.startswith("https://"):
            continue
        key = urlsplit(u).path
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def parse_embed(page: str) -> tuple[list[str], list[str]]:
    """Embed sayfasından (fotoğraf adresleri, video adresleri)."""
    text = _normalize(page)
    videos = _dedupe([_clean(m) for m in _VIDEO.findall(text)])
    images = _dedupe([_clean(m) for m in _DISPLAY.findall(text)])
    if not images:
        images = _dedupe([_clean(m) for m in _IMG_TAG.findall(page)])
    return images, videos


def fetch_media(client, url: str) -> tuple[list[str], list[str]]:
    """Gönderideki (fotoğraflar, videolar). Alınamazsa ([], [])."""
    code = shortcode(url)
    if not code:
        return [], []
    try:
        resp = client.get(embed_url(code), headers={"Accept": "text/html,application/xhtml+xml"})
        resp.raise_for_status()
        return parse_embed(resp.text)
    except Exception:  # noqa: BLE001 - embed kapalı/engelli: çağıran NoMediaError'a çevirir
        return [], []
