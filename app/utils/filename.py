"""Windows uyumlu dosya adı üretimi ve çakışma yönetimi."""
from __future__ import annotations

import glob
import re
from pathlib import Path

FORBIDDEN = '\\/:*?"<>|'
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# "video.mp4.exe" gibi çalıştırılabilir uzantı taklidini etkisizleştirmek için (spec madde 58)
_EXEC_EXT = re.compile(r"\.(exe|bat|cmd|com|scr|msi|dll|ps1|vbs|vbe|js|jse|wsf|lnk|pif|hta|reg)(?=\.|$)", re.IGNORECASE)
_SPACES = re.compile(r"\s+")

CONFLICT_NEW = "new"
CONFLICT_OVERWRITE = "overwrite"
CONFLICT_SKIP = "skip"

NAMING_TITLE = "title"
NAMING_PLATFORM_TITLE = "platform_title"
NAMING_TITLE_ID = "title_id"


def sanitize_filename(name: str, max_len: int = 150, fallback: str = "indirilen_dosya") -> str:
    """Windows'un yasakladığı karakterleri temizler, uzun adı kısaltır."""
    name = _CONTROL.sub("", name or "")
    for ch in FORBIDDEN:
        name = name.replace(ch, "-")
    name = _SPACES.sub(" ", name).strip()
    name = _EXEC_EXT.sub(lambda m: "_" + m.group(1), name)
    name = name[: max(1, max_len)].rstrip(" .")
    if not name:
        return fallback
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name


def max_stem_length(out_dir: Path, extension_reserve: int = 12) -> int:
    """Windows'ta tam yol ~260 karakteri geçmemeli; klasör uzunluğuna göre stem sınırı."""
    return max(40, min(150, 250 - len(str(out_dir)) - extension_reserve))


def build_base_name(
    title: str,
    platform: str = "",
    media_id: str = "",
    style: str = NAMING_TITLE,
    max_len: int = 150,
) -> str:
    title = title or "indirilen_dosya"
    if style == NAMING_PLATFORM_TITLE and platform:
        raw = f"{platform} - {title}"
    elif style == NAMING_TITLE_ID and media_id:
        raw = f"{title} [{media_id}]"
    else:
        raw = title
    return sanitize_filename(raw, max_len=max_len)


def existing_files(out_dir: Path, base: str) -> list[Path]:
    """`base.*` ile eşleşen (yarım kalmış .part hariç) dosyalar."""
    pattern = str(out_dir / (glob.escape(base) + ".*"))
    return [Path(p) for p in glob.glob(pattern) if not p.endswith((".part", ".ytdl", ".temp"))]


def resolve_base_name(out_dir: Path, base: str, policy: str) -> tuple[str, Path | None]:
    """Çakışma politikasına göre kullanılacak ad ve (atlanacaksa) mevcut dosya.

    Döner: (base, skip_path). skip_path None değilse dosya zaten var, indirme atlanmalı.
    """
    found = existing_files(out_dir, base)
    if not found or policy == CONFLICT_OVERWRITE:
        return base, None
    if policy == CONFLICT_SKIP:
        return base, found[0]
    n = 2
    while existing_files(out_dir, f"{base} ({n})"):
        n += 1
    return f"{base} ({n})", None
