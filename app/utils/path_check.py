"""Kullanıcının seçtiği klasör yollarını doğrular (spec 58-60, 70): yazma izni, geçerlilik."""
from __future__ import annotations

import uuid
from pathlib import Path


def validate_download_dir(raw: str) -> tuple[bool, str]:
    """(uygun mu, kullanıcıya gösterilecek mesaj). Klasör yoksa oluşturmayı dener."""
    raw = (raw or "").strip()
    if not raw:
        return False, "Klasör yolu boş."
    if "\0" in raw:
        return False, "Geçersiz klasör yolu."
    path = Path(raw)
    if not path.is_absolute():
        return False, "Tam (mutlak) bir klasör yolu gir, ör. D:\\Indirilenler."
    if ".." in path.parts:
        return False, "Yol '..' içeremez."
    try:
        if path.exists() and not path.is_dir():
            return False, "Bu yol bir klasör değil (aynı adda bir dosya var)."
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False, "Klasör oluşturulamadı. Sürücü bağlı mı / yazma izni var mı?"
    probe = path / f".mit_write_test_{uuid.uuid4().hex[:8]}"
    try:
        probe.write_bytes(b"x")
        probe.unlink()
    except OSError:
        return False, "Bu klasöre yazma izni yok."
    return True, ""
