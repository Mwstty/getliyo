"""Uygulama güncelleme kontrolü (GitHub Releases). Yalnızca BİLGİ verir; otomatik kurulum yapmaz
(güvenlik: imzasız bir dosyayı sessizce çalıştırmayız)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class UpdateInfo:
    ok: bool
    newer: bool = False
    latest: str = ""
    url: str = ""
    message: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def check_app_update(repo: str, current: str, fetch: Optional[Callable[[str], dict]] = None) -> UpdateInfo:
    if not repo or "/" not in repo:
        return UpdateInfo(False, message="Güncelleme kaynağı ayarlanmamış.")
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        if fetch is None:
            import httpx

            resp = httpx.get(api, timeout=10, headers={"Accept": "application/vnd.github+json"})
            resp.raise_for_status()
            data = resp.json()
        else:
            data = fetch(api)
        tag = str(data.get("tag_name") or "")
        url = str(data.get("html_url") or "")
    except Exception:  # noqa: BLE001 - ağ/JSON/404 (özel depo) hepsi kullanıcıya aynı mesaj
        return UpdateInfo(False, message="Güncelleme bilgisi alınamadı (internet ya da depo erişimi).")
    if not tag:
        return UpdateInfo(False, message="Henüz yayınlanmış bir sürüm yok.")
    newer = is_newer(tag, current)
    return UpdateInfo(True, newer, tag.lstrip("vV"), url, "Yeni sürüm var." if newer else "Uygulama güncel.")
