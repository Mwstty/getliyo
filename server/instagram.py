"""Instagram bağlantı doğrulaması: yalnızca içerik bağlantıları (gönderi, reel, IGTV, hikaye) kabul edilir."""
from __future__ import annotations

from urllib.parse import urlsplit

from app.utils.errors import UserError

IG_HOSTS = ("instagram.com", "instagr.am")
_CONTENT = {"p": "post", "reel": "reel", "reels": "reel", "tv": "igtv"}


def is_instagram(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in IG_HOSTS)


def classify(url: str) -> str:
    """'post' | 'reel' | 'igtv' | 'story' | 'other' (profil, giriş sayfası, keşfet vb.)."""
    parts = [p for p in urlsplit(url).path.split("/") if p]
    if not parts:
        return "other"
    if parts[0] == "stories":
        return "story" if len(parts) >= 3 else "other"
    if parts[0] in _CONTENT and len(parts) >= 2:
        return _CONTENT[parts[0]]
    if len(parts) >= 3 and parts[1] in _CONTENT:  # /kullanici/p/KOD/
        return _CONTENT[parts[1]]
    return "other"


def check(url: str) -> None:
    """Instagram bağlantısı içerik göstermiyorsa anlaşılır bir hata verir (kodu: ig_invalid)."""
    if is_instagram(url) and classify(url) == "other":
        raise UserError(
            "Bu bir Instagram içerik bağlantısı değil. Gönderi, reel, IGTV veya hikaye bağlantısını yapıştır.",
            "ig_invalid",
        )
