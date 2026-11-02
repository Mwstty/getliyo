"""Kimlik doğrulama, imzalı indirme bağlantısı, SSRF koruması ve basit hız sınırlayıcı."""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

from app.utils.net_guard import assert_public_url  # noqa: F401 - geriye dönük uyumluluk


def owner_id(api_key: str) -> str:
    """Anahtarın kendisi saklanmaz/loglanmaz; iş sahipliği bu özetle tutulur."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]


def match_key(candidate: str, keys: frozenset[str]) -> str | None:
    """Zamanlama saldırısına dayanıklı anahtar karşılaştırması. Eşleşen anahtarı döndürür."""
    found = None
    for key in keys:
        if hmac.compare_digest(candidate.encode("utf-8"), key.encode("utf-8")):
            found = key
    return found


def sign_download(secret: bytes, job_id: str, expires: int) -> str:
    return hmac.new(secret, f"{job_id}.{expires}".encode("utf-8"), hashlib.sha256).hexdigest()


def verify_download(secret: bytes, job_id: str, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(sign_download(secret, job_id, expires), signature or "")


class RateLimiter:
    """Anahtar başına kayan pencere (dakikada N istek)."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def allow(self, who: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[who]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            self._calls += 1
            if self._calls % 256 == 0:  # süresi dolmuş anahtarları at: bellek sınırsız şişmesin
                for key in [k for k, q in self._hits.items() if not q or now - q[-1] > 60]:
                    del self._hits[key]
            return True
