"""X/Twitter: görsel URL yükseltme ve /photo|video/N deep-link'lerini ayıklama.

KRİTİK BUG DÜZELTMESİ: X'in web arayüzü bir tweeti ".../status/123/photo/2" gibi bir
adresle açar — bu sadece "lightbox'ı 2. öğede aç" demektir, "bu tweette SADECE bu video
var" demek DEĞİLDİR. yt-dlp'nin Twitter extractor'ı bu adresi doğrudan verirsen, o
index'teki öğe video değilse "Media #N is not a video" hatasıyla patlar (fotoğrafı video
sanıp indirmeye zorlamaya çalışır). Çözüm: /photo/N veya /video/N son ekini atıp asıl
tweet adresini analiz etmek — bu, yt-dlp'nin tweetteki TÜM medyayı (foto+video karışık
olsa bile) doğru şekilde döndürmesini sağlar; galeri ekranı zaten bunu gösterebiliyor.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit

_MEDIA_SUFFIX = re.compile(
    r"^(https?://(?:www\.)?(?:x\.com|twitter\.com)/[^/?#]+/status/\d+)"
    r"/(?:photo|video)/(\d+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)


def strip_media_suffix(url: str) -> tuple[str, Optional[int]]:
    """".../status/123/photo/2" -> (".../status/123", 2). Eşleşmezse (url, None) döner."""
    match = _MEDIA_SUFFIX.match(url.strip())
    if not match:
        return url, None
    return match.group(1), int(match.group(2))


def candidate_urls(url: str) -> list[str]:
    parts = urlsplit(url)
    if (parts.hostname or "") != "pbs.twimg.com" or not parts.path.startswith("/media/"):
        return [url]
    query = dict(parse_qsl(parts.query))
    if query.get("name") == "orig":
        return [url]
    query["name"] = "orig"
    return [parts._replace(query=urlencode(query)).geturl(), url]


# ---------------------------------------------------------------- yalnızca fotoğraf içeren tweetler
# yt-dlp'nin Twitter çıkarıcısı sadece VİDEO/GIF arar; fotoğraf tweetlerinde
# "No video could be found in this tweet" hatası verir. Bu durumda tweetin herkese açık
# verisi (syndication + fxtwitter) okunup fotoğraf adresleri çıkarılır.
_STATUS = re.compile(
    r"^https?://(?:www\.|mobile\.)?(?:x\.com|twitter\.com)/([^/?#]+)/status/(\d+)",
    re.IGNORECASE,
)


def parse_status(url: str) -> Optional[tuple[str, str]]:
    """Tweet adresinden (kullanıcı, tweet_id). Tweet adresi değilse None."""
    match = _STATUS.match(url.strip())
    return (match.group(1), match.group(2)) if match else None


def _syndication_token(tweet_id: str) -> str:
    """Syndication uç noktasının beklediği token (yt-dlp ile aynı formül)."""
    import math

    value = (int(tweet_id) / 1e15) * math.pi
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    whole, frac = int(value), value - int(value)
    out = ""
    n = whole
    while n:
        out = digits[n % 36] + out
        n //= 36
    out = out or "0"
    frac_out = ""
    for _ in range(12):
        frac *= 36
        d = int(frac)
        frac_out += digits[d]
        frac -= d
        if not frac:
            break
    return (out + frac_out).replace("0", "").replace(".", "")


def _photos_from_syndication(data: dict) -> list[str]:
    urls: list[str] = []
    for item in data.get("mediaDetails") or []:
        if item.get("type") == "photo" and item.get("media_url_https"):
            urls.append(item["media_url_https"])
    if not urls:
        for item in data.get("photos") or []:
            if item.get("url"):
                urls.append(item["url"])
    return urls


def _photos_from_fx(data: dict) -> list[str]:
    media = (data.get("tweet") or {}).get("media") or {}
    items = media.get("all") or media.get("photos") or []
    return [i["url"] for i in items if i.get("url") and i.get("type", "photo") == "photo"]


def fetch_photo_urls(client, url: str) -> list[str]:
    """Tweetteki fotoğrafların adreslerini (sırayla) döndürür; bulunamazsa boş liste."""
    parsed = parse_status(url)
    if not parsed:
        return []
    user, tweet_id = parsed
    attempts = (
        (
            f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&lang=en&token={_syndication_token(tweet_id)}",
            _photos_from_syndication,
        ),
        (f"https://api.fxtwitter.com/{user}/status/{tweet_id}", _photos_from_fx),
    )
    for endpoint, extract in attempts:
        try:
            resp = client.get(endpoint)
            resp.raise_for_status()
            urls = [u for u in extract(resp.json()) if u.startswith("https://")]
        except Exception:  # noqa: BLE001 - uç nokta kapalı/engelli: sıradakini dene
            continue
        if urls:
            return urls
    return []
