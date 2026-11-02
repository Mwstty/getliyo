"""Kullanıcıya gösterilecek anlaşılır Türkçe hata mesajları."""
from __future__ import annotations

import errno

import httpx

MESSAGES: dict[str, str] = {
    "invalid_url": "Geçersiz URL. Lütfen http:// veya https:// ile başlayan bir bağlantı gir.",
    "not_found": "Kaynak bulunamadı. Bağlantı silinmiş ya da hatalı olabilir.",
    "no_media": "Bu bağlantı için indirilebilir medya bulunamadı veya kaynak desteklenmiyor.",
    "unsupported": "Bu bağlantı için indirilebilir medya bulunamadı veya kaynak desteklenmiyor.",
    "offline": "İnternet bağlantısı gerekli. Bağlantını kontrol edip tekrar dene.",
    "ffmpeg": "FFmpeg bulunamadı. Birleştirme/dönüştürme için gerekli. Ayarlar > Sistem bölümüne bak.",
    "disk": "Disk alanı yetersiz.",
    "download_failed": "İndirme başarısız oldu. Ayrıntılar log dosyasında.",
    "format": "Seçilen format bu kaynak için kullanılamıyor. Başka bir seçenek dene.",
    "not_a_video": "Bu gönderideki medya bir video değil, görsel olarak algılandı.",
    "duplicate": "Bu içerik daha önce indirilmiş.",
    "forbidden": (
        "Kaynak erişime kapalı (özel, giriş gerektiren, yaş/bölge kısıtlı ya da "
        "istek sınırına takılmış olabilir)."
    ),
}


class UserError(Exception):
    """Mesajı doğrudan kullanıcıya gösterilebilen hata."""

    def __init__(self, message: str, key: str = "download_failed") -> None:
        super().__init__(message)
        self.message = message
        self.key = key

    @classmethod
    def from_key(cls, key: str) -> "UserError":
        return cls(MESSAGES.get(key, MESSAGES["download_failed"]), key)


class NoMediaError(UserError):
    """Kaynakta indirilebilir medya bulunamadı / kaynak desteklenmiyor."""

    def __init__(self) -> None:
        super().__init__(MESSAGES["no_media"], "no_media")


class CancelledError(Exception):
    """Kullanıcı indirmeyi iptal etti."""


class SkippedError(Exception):
    """Aynı dosya var ve çakışma davranışı 'atla'."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


_CHECKS: list[tuple[str, tuple[str, ...]]] = [
    ("disk", ("no space left", "errno 28", "disk full")),
    ("ffmpeg", ("ffmpeg is not installed", "ffmpeg not found", "ffprobe and ffmpeg not found")),
    ("format", ("requested format is not available", "requested format not available")),
    ("unsupported", ("unsupported url",)),
    (
        "no_media",
        (
            "no video could be found",
            "no video formats found",
            "no media found",
            "there is no video in this post",
            "no suitable",
        ),
    ),
    (
        "offline",
        (
            "getaddrinfo failed",
            "name or service not known",
            "temporary failure in name resolution",
            "network is unreachable",
            "urlopen error",
            "no address associated",
            "connection refused",
            "timed out",
        ),
    ),
    (
        "forbidden",
        (
            "private video",
            "sign in",
            "log in",
            "login",
            "members-only",
            "confirm your age",
            "age-restricted",
            "not available in your country",
            "geo restrict",
            "geo-restrict",
            "http error 403",
            "http error 401",
            "http error 429",
            "rate-limit",
            "rate limit",
            "cookies",
        ),
    ),
    (
        "not_found",
        (
            "http error 404",
            "video unavailable",
            "this video is unavailable",
            "has been removed",
            "does not exist",
            "no longer available",
            "not found",
        ),
    ),
]


def error_key(exc: BaseException) -> str:
    """İstisnayı bir hata anahtarına çevirir (kullanıcı mesajı için)."""
    if isinstance(exc, UserError):
        return exc.key
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (404, 410):
            return "not_found"
        if code in (401, 403, 429):
            return "forbidden"
        return "download_failed"
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        return "offline"
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ENOSPC:
        return "disk"
    text = str(exc).lower()
    for key, needles in _CHECKS:
        if any(n in text for n in needles):
            return key
    return "download_failed"


def friendly_message(exc: BaseException) -> str:
    if isinstance(exc, UserError):
        return exc.message
    return MESSAGES.get(error_key(exc), MESSAGES["download_failed"])
