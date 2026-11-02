"""Geçmiş üzerindeki dosya işlemleri (aç, göster, sil, toplu sil, bul) — UI'dan bağımsız, test edilebilir.

GÜVENLİK KURALLARI (spec 17, 58):
- "Geçmişten sil" SADECE veritabanı satırını siler.
- Dosya silme yalnızca geçmişte kayıtlı (=uygulamanın indirdiği) DOSYALAR için yapılır,
  klasörlere ASLA dokunulmaz, kullanıcının genel Downloads klasörü topluca temizlenmez.
- Uygulamanın kendi klasörleri (kurulum dizini, AppData) korunur.
- Toplu silmede dosya boyutu kayıttakiyle aynı değilse (kullanıcı sonradan değiştirmiş/
  başka dosyayla değiştirmiş olabilir) o dosya ATLANIR.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from app.history.db import HistoryDB
from app.history.models import HistoryRecord
from app.utils.logger import get_logger
from app.utils.trash import delete_file

log = get_logger("history.service")

_MB = 1024 * 1024


def compute_fingerprint(path: Path) -> str:
    """Hızlı parmak izi: boyut + ilk 1 MB + son 1 MB SHA-256 (dev dosyalarda bile saniyeler)."""
    try:
        size = path.stat().st_size
        h = hashlib.sha256()
        h.update(str(size).encode())
        with open(path, "rb") as fh:
            h.update(fh.read(_MB))
            if size > 2 * _MB:
                fh.seek(-_MB, 2)
                h.update(fh.read(_MB))
        return h.hexdigest()
    except OSError:
        return ""


@dataclass
class BulkResult:
    deleted: int = 0
    skipped: list[tuple[int, str]] = field(default_factory=list)  # (record_id, sebep)


@dataclass
class DuplicateInfo:
    record: HistoryRecord
    file_exists: bool


class HistoryService:
    def __init__(
        self,
        db: HistoryDB,
        protected_roots: Iterable[Path] = (),
        deleter: Callable[[Path, bool], bool] = delete_file,
    ) -> None:
        self.db = db
        self.protected_roots = [Path(p).resolve() for p in protected_roots]
        self._delete = deleter

    # ------------------------------------------------------------------ durum
    @staticmethod
    def file_exists(record: HistoryRecord) -> bool:
        return bool(record.file_path) and Path(record.file_path).is_file()

    def file_status_text(self, record: HistoryRecord) -> str:
        if record.status != "completed":
            return ""
        return "" if self.file_exists(record) else "Dosya bulunamadı"

    # ------------------------------------------------------------------ duplicate
    def check_duplicate(self, url: str, media_id: str = "") -> Optional[DuplicateInfo]:
        rec = self.db.find_duplicate(url, media_id)
        return DuplicateInfo(rec, self.file_exists(rec)) if rec else None

    # ------------------------------------------------------------------ güvenlik
    def _is_protected(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return True
        for root in self.protected_roots:
            if resolved == root or root in resolved.parents:
                return True
        return False

    def can_delete_file(self, record: HistoryRecord, *, strict: bool) -> tuple[bool, str]:
        """strict=True (toplu işlem): boyut kayıttakiyle aynı olmalı."""
        if not record.file_path:
            return False, "Dosya yolu kayıtlı değil"
        path = Path(record.file_path)
        if not path.exists():
            return False, "Dosya bulunamadı"
        if not path.is_file() or path.is_symlink():
            return False, "Bir dosya değil (klasörlere dokunulmaz)"
        if self._is_protected(path):
            return False, "Uygulamanın kendi klasörü (korumalı)"
        if strict and record.file_size is not None:
            try:
                if path.stat().st_size != record.file_size:
                    return False, "Dosya indirildikten sonra değişmiş"
            except OSError:
                return False, "Dosyaya erişilemiyor"
        return True, ""

    # ------------------------------------------------------------------ silme
    def delete_from_history(self, ids: list[int]) -> int:
        """SADECE veritabanı kaydı. Fiziksel dosyaya dokunmaz."""
        if ids:
            self.db.delete_records(ids)
        return len(ids)

    def delete_file_and_record(self, record_id: int, use_recycle_bin: bool) -> tuple[bool, str]:
        """Tek kayıt: (kullanıcı onayı UI'da alınmış olmalı) dosyayı sil + kaydı sil."""
        rec = self.db.get(record_id)
        if not rec:
            return False, "Kayıt bulunamadı"
        ok, reason = self.can_delete_file(rec, strict=False)
        if not ok and reason != "Dosya bulunamadı":
            return False, reason
        if ok and not self._delete(Path(rec.file_path), use_recycle_bin):
            return False, "Dosya silinemedi (kullanımda olabilir)"
        self.db.delete_record(record_id)
        return True, ""

    def delete_files_bulk(self, ids: list[int], use_recycle_bin: bool) -> BulkResult:
        result = BulkResult()
        for rid in ids:
            rec = self.db.get(rid)
            if not rec:
                continue
            ok, reason = self.can_delete_file(rec, strict=True)
            if not ok:
                if reason == "Dosya bulunamadı":  # zaten yok: kaydı temizlemek sorun değil
                    self.db.delete_record(rid)
                    result.deleted += 1
                else:
                    result.skipped.append((rid, reason))
                continue
            if self._delete(Path(rec.file_path), use_recycle_bin):
                self.db.delete_record(rid)
                result.deleted += 1
            else:
                result.skipped.append((rid, "Dosya silinemedi (kullanımda olabilir)"))
        return result

    def clear_history(self) -> None:
        """Tüm geçmiş kayıtları — dosyalara DOKUNMAZ."""
        self.db.clear_all()

    def clear_history_and_files(self, use_recycle_bin: bool) -> BulkResult:
        """Geçmişteki (yani uygulamanın indirdiği) dosyaları ve kayıtları siler.
        Geçmişte olmayan hiçbir dosyaya dokunmaz."""
        ids = [r.id for r in self.db.list(limit=10**9)]
        result = self.delete_files_bulk(ids, use_recycle_bin)
        # dosyası silinemeyen/atlanan kayıtlar geçmişte kalır ki kullanıcı görebilsin
        return result

    # ------------------------------------------------------------------ crash recovery
    @staticmethod
    def partial_files(record: HistoryRecord) -> list[Path]:
        """Bu kayda ait yarım kalmış geçici dosyalar (.part/.ytdl) — SADECE aynı ada sahip olanlar."""
        if not record.file_path:
            return []
        p = Path(record.file_path)
        folder, stem = p.parent, p.stem
        if not folder.is_dir():
            return []
        import glob

        found = []
        for pattern in (f"{glob.escape(stem)}*.part", f"{glob.escape(stem)}*.ytdl"):
            found += [Path(x) for x in glob.glob(str(folder / pattern))]
        return found

    def discard_stale(self, records: list[HistoryRecord]) -> int:
        """Yarım kalan indirmeleri iptal eder: geçici dosyalarını siler, kaydı 'cancelled' yapar."""
        for rec in records:
            for f in self.partial_files(rec):
                try:
                    f.unlink()
                except OSError:
                    log.warning("Geçici dosya silinemedi: %s", f.name)
            self.db.mark_status(rec.id, "cancelled")
        return len(records)

    # ------------------------------------------------------------------ dosya taşındı
    def relink(self, record_id: int, new_path: Path) -> bool:
        if not new_path.is_file():
            return False
        self.db.update_path(record_id, str(new_path))
        return True
