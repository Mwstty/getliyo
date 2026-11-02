"""Serbest şablon tabanlı dosya adlandırma (spec madde 21): {title} {uploader} {date} {platform} {id}."""
from __future__ import annotations

import re
from datetime import date as _date
from typing import Optional

from app.utils.filename import sanitize_filename

_TOKEN = re.compile(r"\{(title|uploader|date|platform|id)\}")

DEFAULT_TEMPLATE = "{title}"

PRESET_TEMPLATES: list[tuple[str, str]] = [
    ("{title}", "Başlık"),
    ("{platform} - {title}", "Platform - Başlık"),
    ("{title} [{id}]", "Başlık [ID]"),
    ("{uploader} - {title}", "Yükleyen - Başlık"),
    ("{date} - {title}", "Tarih - Başlık"),
]


def render_template(
    template: str,
    *,
    title: str = "",
    uploader: str = "",
    platform: str = "",
    media_id: str = "",
    when: Optional[_date] = None,
    max_len: int = 150,
) -> str:
    """Şablondaki {token}'ları doldurur, sonucu Windows için güvenli hale getirir.

    Boş kalan token'lar (ör. uploader bilinmiyorsa) sessizce çıkarılır, artık ayraçlar
    ("- " gibi) temizlenir — sonuçta "- Başlık" değil "Başlık" görünür.
    """
    values = {
        "title": title.strip(),
        "uploader": uploader.strip(),
        "platform": platform.strip(),
        "id": media_id.strip(),
        "date": (when or _date.today()).isoformat(),
    }
    if not values["title"]:
        values["title"] = "indirilen_dosya"

    def repl(m: re.Match) -> str:
        return values.get(m.group(1), "")

    rendered = _TOKEN.sub(repl, template or DEFAULT_TEMPLATE)
    # Bos token'lardan kalan cift bosluk/ayrac artiklarini temizle: "Kanal -  - Baslik" -> "Kanal - Baslik"
    rendered = re.sub(r"\s*-\s*-\s*", " - ", rendered)
    rendered = re.sub(r"^\s*-\s*|\s*-\s*$", "", rendered)
    rendered = re.sub(r"\s{2,}", " ", rendered).strip()
    if not rendered:
        rendered = values["title"]
    return sanitize_filename(rendered, max_len=max_len)


def validate_template(template: str) -> bool:
    """Kullanıcının girdiği şablonda bilinmeyen {token} var mı kontrolü."""
    if not template.strip():
        return False
    unknown = re.findall(r"\{([a-zA-Z_]+)\}", template)
    known = {"title", "uploader", "date", "platform", "id"}
    return all(tok in known for tok in unknown)
