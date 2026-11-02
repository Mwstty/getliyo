"""İndirme klasörü organizasyonu (spec madde 22): Platform / Medya türü / Tarih alt klasörleri."""
from __future__ import annotations

from datetime import date as _date
from pathlib import Path
from typing import Optional

from app.utils.filename import sanitize_filename

TYPE_NAMES = {"video": "Video", "image": "Image", "audio": "Audio"}


def organized_dir(
    base: Path,
    *,
    platform: str = "",
    kind: str = "",
    by_platform: bool = False,
    by_type: bool = False,
    by_date: bool = False,
    when: Optional[_date] = None,
) -> Path:
    """base\\YouTube\\Video\\2026\\09 gibi. Her parça sanitize edilir (path traversal yok)."""
    parts: list[str] = []
    if by_platform:
        parts.append(sanitize_filename(platform or "Diğer", 60, "Diğer"))
    if by_type and kind:
        parts.append(TYPE_NAMES.get(kind, sanitize_filename(kind, 30)))
    if by_date:
        d = when or _date.today()
        parts += [f"{d.year:04d}", f"{d.month:02d}"]
    out = base
    for part in parts:
        out = out / part
    return out
