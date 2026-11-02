"""Geçmiş (history) veritabanı kayıt modeli."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

STATUS_DOWNLOADING = "downloading"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class HistoryRecord:
    id: int
    title: str
    url: str
    platform: str
    media_type: str  # video / image / audio
    file_path: str
    file_name: str
    file_size: Optional[int]
    resolution: str
    thumbnail: str
    downloaded_at: str  # ISO 8601, UTC
    status: str
    duration: Optional[float]
    is_favorite: bool = False
    media_id: str = ""  # yt-dlp id (duplicate detection için)
    format_container: str = ""
    error_message: str = ""  # başarısız indirmede kullanıcıya gösterilen sebep (Hata Merkezi)
    fingerprint: str = ""  # dosya parmak izi (boyut + baş/son 1 MB hash) — duplicate tespiti için
