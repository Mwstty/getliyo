"""TikTok: yt-dlp'nin desteklemediği fotoğraf gönderileri (/photo/ID) için sayfa verisi taraması.

TikTok sayfaları, gönderi verisini <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"> (eski
sürümde SIGI_STATE) içinde JSON olarak taşır. Fotoğraf gönderisinde imagePost.images altında
her fotoğrafın adresi, music altında da gönderinin sesi bulunur. Video gönderileri yt-dlp ile
inmeye devam eder.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

_SCRIPT = re.compile(
    r'<script[^>]+id="(?:__UNIVERSAL_DATA_FOR_REHYDRATION__|SIGI_STATE)"[^>]*>(.*?)</script>',
    re.DOTALL,
)


@dataclass
class TikTokPost:
    post_id: str = ""
    author: str = ""
    description: str = ""
    images: list[str] = field(default_factory=list)
    audio: str = ""


def _find_item(data: Any) -> Optional[dict]:
    """JSON içinde gönderi nesnesini (itemStruct / ItemModule) bulur."""
    if not isinstance(data, dict):
        return None
    scope = data.get("__DEFAULT_SCOPE__")
    if isinstance(scope, dict):
        for value in scope.values():
            item = ((value or {}).get("itemInfo") or {}).get("itemStruct") if isinstance(value, dict) else None
            if isinstance(item, dict):
                return item
    module = data.get("ItemModule")
    if isinstance(module, dict):
        for value in module.values():
            if isinstance(value, dict):
                return value
    return None


def parse_page(page: str) -> Optional[TikTokPost]:
    match = _SCRIPT.search(page)
    if not match:
        return None
    try:
        item = _find_item(json.loads(match.group(1)))
    except ValueError:
        return None
    if not item:
        return None
    images: list[str] = []
    for img in ((item.get("imagePost") or {}).get("images") or []):
        urls = ((img or {}).get("imageURL") or {}).get("urlList") or []
        url = next((u for u in urls if isinstance(u, str) and u.startswith("https://")), "")
        if url and url not in images:
            images.append(url)
    author = item.get("author")
    if isinstance(author, dict):
        author = author.get("uniqueId") or author.get("nickname") or ""
    music = item.get("music") or {}
    return TikTokPost(
        post_id=str(item.get("id") or ""),
        author=str(author or ""),
        description=str(item.get("desc") or ""),
        images=images,
        audio=music.get("playUrl") if isinstance(music.get("playUrl"), str) else "",
    )


def fetch_post(client, url: str) -> Optional[TikTokPost]:
    """Kısa bağlantılar (vm./vt.tiktok.com) yönlendirmeyle çözülür. Alınamazsa None."""
    try:
        resp = client.get(url, headers={"Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"})
        resp.raise_for_status()
        return parse_page(resp.text)
    except Exception:  # noqa: BLE001 - sayfa kapalı/engelli: çağıran NoMediaError'a çevirir
        return None
