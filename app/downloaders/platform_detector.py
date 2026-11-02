"""URL'den platformu algılar."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from app.downloaders.http_utils import url_extension
from app.media.media_utils import AUDIO_EXTS, IMAGE_EXTS, VIDEO_EXTS

DIRECT_NAME = "Doğrudan medya URL'si"
OTHER_NAME = "Diğer web sitesi"

# ad -> (alan adları, yt-dlp bulamazsa HTML taraması denensin mi)
PLATFORMS: dict[str, tuple[tuple[str, ...], bool]] = {
    "YouTube": (("youtube.com", "youtu.be", "youtube-nocookie.com"), False),
    "Instagram": (("instagram.com", "instagr.am"), False),
    "X": (("x.com", "twitter.com", "t.co"), False),
    "TikTok": (("tiktok.com",), False),
    "Facebook": (("facebook.com", "fb.watch", "fb.com"), False),
    "Reddit": (("reddit.com", "redd.it"), False),
    "Pinterest": (("pinterest.com", "pin.it", "pinimg.com"), True),
    "Twitch": (("twitch.tv",), False),
}

# Uzantısı olmasa da doğrudan görsel/medya sunan bilinen CDN alan adları
DIRECT_HOSTS: dict[str, str] = {
    "pbs.twimg.com": "X",
    "i.redd.it": "Reddit",
    "preview.redd.it": "Reddit",
    "i.pinimg.com": "Pinterest",
    "lh3.googleusercontent.com": "Google Images",
    "encrypted-tbn0.gstatic.com": "Google Images",
    "encrypted-tbn1.gstatic.com": "Google Images",
    "encrypted-tbn2.gstatic.com": "Google Images",
    "encrypted-tbn3.gstatic.com": "Google Images",
}


@dataclass(frozen=True)
class PlatformInfo:
    name: str
    is_direct_media: bool = False
    html_fallback: bool = True  # yt-dlp bulamazsa sayfa taraması (og:image, <video> ...) denensin mi


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _is_google_images(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    labels = host.split(".")
    if "google" not in labels:
        return False
    return parts.path.startswith("/imgres") or "isch" in parse_qs(parts.query).get("tbm", []) or host.startswith("images.google.")


def resolve_url(url: str) -> str:
    """Google Görseller /imgres bağlantılarındaki gerçek görsel adresini (imgurl) çıkarır."""
    if _is_google_images(url):
        imgurl = parse_qs(urlsplit(url).query).get("imgurl", [""])[0]
        if imgurl.startswith(("http://", "https://")):
            return imgurl
    return url


def detect_platform(url: str) -> PlatformInfo:
    host = _host(url)
    ext = url_extension(url)
    has_media_ext = ext in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

    for direct_host, name in DIRECT_HOSTS.items():
        if host == direct_host:
            return PlatformInfo(name, is_direct_media=True)
    if _is_google_images(url):
        return PlatformInfo("Google Images", is_direct_media=False, html_fallback=True)
    for name, (domains, fallback) in PLATFORMS.items():
        if any(_matches(host, d) for d in domains):
            return PlatformInfo(name, is_direct_media=has_media_ext, html_fallback=fallback)
    if has_media_ext:
        return PlatformInfo(DIRECT_NAME, is_direct_media=True)
    return PlatformInfo(OTHER_NAME, is_direct_media=False, html_fallback=True)
