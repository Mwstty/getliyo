"""URL normalizasyonu: aynı içeriğe işaret eden farklı yazımları tek bir cache anahtarına indirger.

DİKKATLİ: servis için ANLAMLI olabilecek query parametrelerini KÖRLEMESİNE silmiyoruz (spec
madde 2) — sadece bilinen, içerikle ilgisiz takip (tracking) parametrelerini çıkarıyoruz.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PARAMS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
        "fbclid", "gclid", "gclsrc", "ref_src", "ref_url", "igshid",
    }
)


def normalize_url(url: str) -> str:
    """Cache/duplicate-kontrolü için kanonik biçim: küçük harf şema+host, iz parametreleri
    çıkarılmış ve sıralanmış query, sondaki '/' temizlenmiş path, fragment yok."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING_PARAMS]
    pairs.sort()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(pairs), ""))
