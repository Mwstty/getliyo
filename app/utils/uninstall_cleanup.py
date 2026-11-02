"""Installer'ın (Inno Setup) çağırdığı, kaldırma sırasında kullanıcı onayına göre veri temizliği.

Yalnızca --uninstall-cleanup ile çağrıldığında çalışır; hiçbir GUI açmaz, hızlıca çıkar.
Aynı, zaten test edilmiş HistoryService güvenlik kurallarını kullanır: "downloads" seçeneği
SADECE geçmişte kayıtlı (uygulamanın indirdiği) dosyaları siler, hiçbir klasörü toptan silmez.
"""
from __future__ import annotations

import argparse
import shutil

from app.utils.logger import get_logger
from app.utils.paths import appdata_dir

log = get_logger("uninstall")


def run_cleanup(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--logs", action="store_true")
    parser.add_argument("--downloads", action="store_true")
    args, _ = parser.parse_known_args(argv)

    root = appdata_dir()

    if args.downloads:
        # ÖNCE (history.db silinmeden önce) geçmişteki dosyaları güvenli şekilde sil.
        try:
            from app.history.db import HistoryDB
            from app.history.service import HistoryService

            db = HistoryDB(root / "history.db")
            svc = HistoryService(db, protected_roots=[root])
            ids = [r.id for r in db.list(limit=10**9)]
            result = svc.delete_files_bulk(ids, use_recycle_bin=True)
            log.info("Kaldırma: %s dosya silindi, %s atlandı", result.deleted, len(result.skipped))
            db.close()
        except Exception:  # noqa: BLE001 - kaldırma sırasında hataya rağmen devam et
            log.exception("Kaldırma: indirilen dosyalar silinirken hata")

    if args.history:
        _remove_file(root / "history.db")
    if args.settings:
        _remove_file(root / "settings.json")
    if args.cache:
        _remove_dir(root / "cache")
    if args.logs:
        _remove_dir(root / "logs")
    return 0


def _remove_file(path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        log.warning("Kaldırma: silinemedi: %s", path)


def _remove_dir(path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        log.warning("Kaldırma: klasör silinemedi: %s", path)
