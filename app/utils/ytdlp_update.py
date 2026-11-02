"""yt-dlp sürüm kontrolü (arayüzden bağımsız; masaüstü ve ileride sunucu aynı kodu kullanır)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class YtdlpStatus:
    current: str
    latest: Optional[str]  # ağ hatasında None

    @property
    def newer(self) -> bool:
        return self.latest is not None and _norm(self.latest) > _norm(self.current)


def _norm(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.replace("-", ".").split(".") if p.isdigit())


def check_ytdlp() -> YtdlpStatus:
    """Kurulu sürüm ile PyPI'daki son sürümü karşılaştırır. Ağ hatası fırlatmaz."""
    import httpx
    from yt_dlp.version import __version__

    try:
        resp = httpx.get("https://pypi.org/pypi/yt-dlp/json", timeout=10)
        resp.raise_for_status()
        return YtdlpStatus(__version__, resp.json()["info"]["version"])
    except (httpx.HTTPError, KeyError, ValueError):
        return YtdlpStatus(__version__, None)
