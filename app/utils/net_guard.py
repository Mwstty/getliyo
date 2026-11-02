"""Sunucu modunda iç ağa / localhost'a / bulut metadata adresine çıkışı engeller (SSRF).

Masaüstü uygulamasında kapalıdır (kullanıcı kendi ağındaki adresleri indirebilir); yalnızca
bağımsız sunucu (`python -m server`) açar. Her HTTP isteğinde (yönlendirmeler dahil) çağrılır."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.utils.errors import UserError

_PUBLIC_ONLY = False


def set_public_only(enabled: bool) -> None:
    global _PUBLIC_ONLY
    _PUBLIC_ONLY = bool(enabled)


_ALLOWED_HOSTS: set[str] = set()
_ORIG_GETADDRINFO = socket.getaddrinfo
_installed = False


def allow_host(host: str) -> None:
    """Bilerek erişilecek iç adres (ör. yapılandırılmış çıkış proxy'si) için istisna."""
    if host:
        _ALLOWED_HOSTS.add(host.lower())


def _is_blocked(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text.split("%")[0])
    mapped = getattr(ip, "ipv4_mapped", None)  # ::ffff:127.0.0.1 gibi sarmalanmış adresler
    return not (mapped or ip).is_global


def _guarded_getaddrinfo(host, port, *args, **kwargs):
    infos = _ORIG_GETADDRINFO(host, port, *args, **kwargs)
    flags = kwargs.get("flags", args[3] if len(args) > 3 else 0)
    if not _PUBLIC_ONLY or flags & socket.AI_PASSIVE:  # AI_PASSIVE: sunucunun kendi dinleme adresi
        return infos
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host and str(host).lower() in _ALLOWED_HOSTS:
        return infos
    if any(_is_blocked(i[4][0]) for i in infos):
        raise socket.gaierror(socket.EAI_NONAME, "Bu adrese erişim izni yok.")
    return infos


def install_resolver_guard() -> None:
    """DNS çözümleme anında iç adresleri reddeder. httpx ve yt-dlp dahil TÜM giden bağlantıları kapsar
    ve çözümleme ile bağlanma arasındaki DNS rebinding boşluğunu kapatır (bağlantı çözülen IP'ye kurulur)."""
    global _installed
    if not _installed:
        socket.getaddrinfo = _guarded_getaddrinfo
        _installed = True


def assert_public_url(url: str, *, allow_private: bool = False) -> None:
    if allow_private:
        return
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise UserError.from_key("offline") from None
    for info in infos:
        if _is_blocked(info[4][0]):
            raise UserError("Bu adrese erişim izni yok.", "forbidden")


def guard_request(request) -> None:  # httpx event hook: yönlendirmeler dahil her istekte
    if _PUBLIC_ONLY:
        assert_public_url(str(request.url))
