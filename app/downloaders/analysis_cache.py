"""Aynı URL için gereksiz tekrar analiz/network isteğini önleyen, TTL'li, thread-safe cache.

Performans spec'i (madde D): "Aynı URL için gereksiz network isteği yapılmamalı." ama
kısa ömürlü direct-URL/token/auth bilgileri sonsuza kadar cache'lenmemeli -> TTL kullanılır.
"""
from __future__ import annotations

import copy
import threading
import time
from typing import Optional

from app.downloaders.base_downloader import MediaInfo


class AnalysisCache:
    """Basit, thread-safe, TTL'li in-memory analiz cache'i."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, MediaInfo]] = {}

    def get(self, key: str) -> Optional[MediaInfo]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            timestamp, info = entry
            if time.monotonic() - timestamp > self.ttl_seconds:
                del self._store[key]
                return None
            # Çağıran taraf döneni mutasyona uğratabilir (örn. thumbnail_bytes) -- cache'teki
            # orijinali korumak için bağımsız bir kopya döndürülür.
            return copy.deepcopy(info)

    def set(self, key: str, info: MediaInfo) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), copy.deepcopy(info))

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
