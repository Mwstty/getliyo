"""Platforma özel küçük yardımcılar. yt-dlp'nin zaten yaptığı işi burada tekrarlamıyoruz."""
from __future__ import annotations

from app.platforms import pinterest, twitter


def image_candidates(url: str) -> list[str]:
    """Bir görsel URL'si için denenecek adresler (en yüksek çözünürlük önce, orijinal en sonda)."""
    for module in (pinterest, twitter):
        urls = module.candidate_urls(url)
        if urls != [url]:
            return urls
    return [url]
