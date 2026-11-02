"""Küçük resim önbelleği (spec madde 53): aynı thumbnail tekrar indirilmez, bozuk cache UI'yi çökertmez."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable, Optional

from app.utils.logger import get_logger

log = get_logger("thumbs")
MAX_BYTES = 3_000_000


class ThumbCache:
    def __init__(self, folder: Path, fetch: Callable[[str], Optional[bytes]]) -> None:
        self.folder, self._fetch = folder, fetch

    def _path(self, url: str) -> Path:
        return self.folder / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".img")

    def get(self, url: str) -> Optional[bytes]:
        """Önce diskten; yoksa indirip yazar. Hata olursa None (asla istisna fırlatmaz)."""
        if not url:
            return None
        try:
            path = self._path(url)
            if path.is_file():
                data = path.read_bytes()
                if data:
                    return data
                path.unlink(missing_ok=True)  # boş/bozuk cache dosyası
            data = self._fetch(url)
            if not data or len(data) > MAX_BYTES:
                return None
            self.folder.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return data
        except Exception:  # noqa: BLE001
            log.info("Thumbnail cache hatası (yok sayıldı)")
            return None

    def clear(self) -> int:
        n = 0
        if self.folder.is_dir():
            for f in self.folder.glob("*.img"):
                try:
                    f.unlink(); n += 1
                except OSError:
                    pass
        return n
