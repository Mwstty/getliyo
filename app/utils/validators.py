"""URL doğrulama. Yalnızca http/https kabul edilir."""
from __future__ import annotations

from urllib.parse import urlsplit

from app.utils.errors import UserError

MAX_URL_LENGTH = 4096


def validate_url(raw: str) -> str:
    """Girilen metni doğrular ve temizlenmiş URL'yi döndürür; geçersizse UserError fırlatır."""
    url = (raw or "").strip()
    if not url or len(url) > MAX_URL_LENGTH or any(c.isspace() for c in url):
        raise UserError.from_key("invalid_url")
    if "://" not in url and "." in url and not url.startswith(("/", "\\")):
        url = "https://" + url  # "youtube.com/..." yapıştırılırsa
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        raise UserError.from_key("invalid_url") from None
    if parts.scheme not in ("http", "https") or not host or "." not in host:
        raise UserError.from_key("invalid_url")
    return url


def is_valid_url(raw: str) -> bool:
    try:
        validate_url(raw)
    except UserError:
        return False
    return True
