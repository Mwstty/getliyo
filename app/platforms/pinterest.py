"""Pinterest: küçük boyutlu pinimg adreslerini orijinal boyuta çevirmeyi dener."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

_SIZE_DIR = re.compile(r"^/(\d+x|\d+x\d+|75x75_RS)/", re.IGNORECASE)


def candidate_urls(url: str) -> list[str]:
    parts = urlsplit(url)
    if not (parts.hostname or "").endswith("pinimg.com"):
        return [url]
    upgraded = _SIZE_DIR.sub("/originals/", parts.path, count=1)
    if upgraded == parts.path:
        return [url]
    return [parts._replace(path=upgraded).geturl(), url]
