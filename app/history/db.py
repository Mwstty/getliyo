"""SQLite tabanlı indirme geçmişi. Tek dosya, %APPDATA%\\getliyo\\history.db.

Tasarım notları (bkz. spec madde 15-20, 45, 52, 75):
- Şema sürümlü (PRAGMA user_version); ileride alan eklenirse migration burada yapılır,
  MEVCUT KAYITLAR SİLİNMEZ.
- "Geçmişten sil" SADECE veritabanı satırını siler, fiziksel dosyaya dokunmaz.
- "Dosyayı sil" ayrı bir metottur (fiziksel silme çağrısı UI/utils.trash tarafında yapılır,
  burada sadece kayıt güncellenir/silinir).
- Büyük geçmişlerde performans için (title, url, platform, downloaded_at) üzerinde index var,
  liste sorguları LIMIT/OFFSET ile sayfalanır (lazy loading).
- Duplicate detection: aynı (url, media_id) ikilisiyle daha önce TAMAMLANMIŞ bir kayıt var mı
  diye bakılır.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from app.history.models import STATUS_COMPLETED, STATUS_DOWNLOADING, HistoryRecord
from app.utils.logger import get_logger
from app.utils.paths import appdata_dir

log = get_logger("history")

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    media_type TEXT NOT NULL DEFAULT '',
    file_path TEXT NOT NULL DEFAULT '',
    file_name TEXT NOT NULL DEFAULT '',
    file_size INTEGER,
    resolution TEXT NOT NULL DEFAULT '',
    thumbnail TEXT NOT NULL DEFAULT '',
    downloaded_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    duration REAL,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    media_id TEXT NOT NULL DEFAULT '',
    format_container TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    fingerprint TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_history_downloaded_at ON history(downloaded_at);
CREATE INDEX IF NOT EXISTS idx_history_platform ON history(platform);
CREATE INDEX IF NOT EXISTS idx_history_media_type ON history(media_type);
CREATE INDEX IF NOT EXISTS idx_history_url_media_id ON history(url, media_id);
CREATE INDEX IF NOT EXISTS idx_history_status ON history(status);
"""

# Sürüm sürüm migration adımları. Mevcut kayıtlar ASLA silinmez, sadece sütun eklenir.
_MIGRATIONS: dict[int, list[tuple[str, str]]] = {
    2: [
        ("error_message", "ALTER TABLE history ADD COLUMN error_message TEXT NOT NULL DEFAULT ''"),
        ("fingerprint", "ALTER TABLE history ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''"),
    ],
}


def default_db_path() -> Path:
    return appdata_dir() / "history.db"


class HistoryDB:
    """Thread-safe basit sarmalayıcı (SQLite bağlantısı thread-local)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or default_db_path()
        self._local = threading.local()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate(conn)

    # ------------------------------------------------------------------ altyapı
    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        if current >= SCHEMA_VERSION:
            return
        existing = {r[1] for r in conn.execute("PRAGMA table_info(history)").fetchall()}
        for version in sorted(_MIGRATIONS):
            if version <= current:
                continue
            for column, ddl in _MIGRATIONS[version]:
                if column not in existing:  # taze v2 DB'de sütun zaten var
                    conn.execute(ddl)
                    existing.add(column)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        log.info("Geçmiş veritabanı v%s -> v%s sürümüne yükseltildi", current, SCHEMA_VERSION)

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(
            id=row["id"],
            title=row["title"],
            url=row["url"],
            platform=row["platform"],
            media_type=row["media_type"],
            file_path=row["file_path"],
            file_name=row["file_name"],
            file_size=row["file_size"],
            resolution=row["resolution"],
            thumbnail=row["thumbnail"],
            downloaded_at=row["downloaded_at"],
            status=row["status"],
            duration=row["duration"],
            is_favorite=bool(row["is_favorite"]),
            media_id=row["media_id"],
            format_container=row["format_container"],
            error_message=row["error_message"],
            fingerprint=row["fingerprint"],
        )

    # ------------------------------------------------------------------ yazma
    def start(
        self,
        *,
        title: str,
        url: str,
        platform: str,
        media_type: str,
        file_path: str,
        file_name: str,
        resolution: str = "",
        thumbnail: str = "",
        duration: Optional[float] = None,
        media_id: str = "",
        format_container: str = "",
        downloaded_at: str,
    ) -> int:
        """İndirme başlarken bir satır açar (durum: downloading). Crash recovery bunu kullanır."""
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO history
                   (title, url, platform, media_type, file_path, file_name, resolution,
                    thumbnail, downloaded_at, status, duration, media_id, format_container)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    title, url, platform, media_type, file_path, file_name, resolution,
                    thumbnail, downloaded_at, STATUS_DOWNLOADING, duration, media_id,
                    format_container,
                ),
            )
            return int(cur.lastrowid)

    def mark_status(
        self,
        record_id: int,
        status: str,
        *,
        file_size: Optional[int] = None,
        file_path: Optional[str] = None,
        error_message: Optional[str] = None,
        fingerprint: Optional[str] = None,
    ) -> None:
        sets, params = ["status=?"], [status]
        if file_size is not None:
            sets.append("file_size=?"); params.append(file_size)
        if file_path is not None:
            sets.append("file_path=?"); params.append(file_path)
            sets.append("file_name=?"); params.append(Path(file_path).name)
        if error_message is not None:
            sets.append("error_message=?"); params.append(error_message)
        if fingerprint is not None:
            sets.append("fingerprint=?"); params.append(fingerprint)
        params.append(record_id)
        with self._cursor() as cur:
            cur.execute(f"UPDATE history SET {', '.join(sets)} WHERE id=?", params)

    def set_favorite(self, record_id: int, favorite: bool) -> None:
        with self._cursor() as cur:
            cur.execute("UPDATE history SET is_favorite=? WHERE id=?", (int(favorite), record_id))

    def update_path(self, record_id: int, new_path: str) -> None:
        """Kullanıcı 'Dosyayı Bul' ile taşınmış dosyanın yeni konumunu gösterdiğinde."""
        with self._cursor() as cur:
            cur.execute(
                "UPDATE history SET file_path=?, file_name=? WHERE id=?",
                (new_path, Path(new_path).name, record_id),
            )

    # ------------------------------------------------------------------ silme
    def delete_record(self, record_id: int) -> None:
        """SADECE veritabanı kaydı — fiziksel dosyaya dokunmaz."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM history WHERE id=?", (record_id,))

    def delete_records(self, record_ids: list[int]) -> None:
        with self._cursor() as cur:
            cur.executemany("DELETE FROM history WHERE id=?", [(i,) for i in record_ids])

    def clear_all(self) -> None:
        """Tüm geçmiş kayıtlarını siler — fiziksel dosyalara DOKUNMAZ."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM history")

    # ------------------------------------------------------------------ okuma
    def get(self, record_id: int) -> Optional[HistoryRecord]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM history WHERE id=?", (record_id,))
            row = cur.fetchone()
            return self._row_to_record(row) if row else None

    def list(
        self,
        *,
        search: str = "",
        platform: str = "",
        media_type: str = "",
        since_iso: str = "",
        favorites_only: bool = False,
        statuses: Optional[tuple[str, ...]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HistoryRecord]:
        """Filtrelenmiş, sayfalanmış liste (en yeni önce). Büyük geçmişte lazy-loading içindir."""
        clauses = ["1=1"]
        params: list = []
        if search:
            clauses.append("(title LIKE ? OR url LIKE ?)")
            like = f"%{search}%"
            params += [like, like]
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if media_type:
            clauses.append("media_type = ?")
            params.append(media_type)
        if since_iso:
            clauses.append("downloaded_at >= ?")
            params.append(since_iso)
        if favorites_only:
            clauses.append("is_favorite = 1")
        if statuses:
            clauses.append("status IN (" + ",".join("?" * len(statuses)) + ")")
            params += list(statuses)
        query = (
            "SELECT * FROM history WHERE " + " AND ".join(clauses) +
            " ORDER BY downloaded_at DESC LIMIT ? OFFSET ?"
        )
        params += [limit, offset]
        with self._cursor() as cur:
            cur.execute(query, params)
            return [self._row_to_record(r) for r in cur.fetchall()]

    def count(
        self,
        *,
        search: str = "",
        platform: str = "",
        media_type: str = "",
        since_iso: str = "",
        favorites_only: bool = False,
        statuses: Optional[tuple[str, ...]] = None,
    ) -> int:
        clauses = ["1=1"]
        params: list = []
        if search:
            clauses.append("(title LIKE ? OR url LIKE ?)")
            like = f"%{search}%"
            params += [like, like]
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if media_type:
            clauses.append("media_type = ?")
            params.append(media_type)
        if since_iso:
            clauses.append("downloaded_at >= ?")
            params.append(since_iso)
        if favorites_only:
            clauses.append("is_favorite = 1")
        if statuses:
            clauses.append("status IN (" + ",".join("?" * len(statuses)) + ")")
            params += list(statuses)
        query = "SELECT COUNT(*) FROM history WHERE " + " AND ".join(clauses)
        with self._cursor() as cur:
            cur.execute(query, params)
            return int(cur.fetchone()[0])

    def platforms(self) -> list[str]:
        with self._cursor() as cur:
            cur.execute("SELECT DISTINCT platform FROM history WHERE platform != '' ORDER BY platform")
            return [r[0] for r in cur.fetchall()]

    def find_duplicate(self, url: str, media_id: str = "") -> Optional[HistoryRecord]:
        """Aynı (url, media_id) ile daha önce TAMAMLANMIŞ bir indirme var mı?"""
        with self._cursor() as cur:
            if media_id:
                cur.execute(
                    "SELECT * FROM history WHERE status=? AND (url=? OR (media_id!='' AND media_id=?)) "
                    "ORDER BY downloaded_at DESC LIMIT 1",
                    (STATUS_COMPLETED, url, media_id),
                )
            else:
                cur.execute(
                    "SELECT * FROM history WHERE status=? AND url=? ORDER BY downloaded_at DESC LIMIT 1",
                    (STATUS_COMPLETED, url),
                )
            row = cur.fetchone()
            return self._row_to_record(row) if row else None

    def find_by_fingerprint(self, fingerprint: str, exclude_id: int = 0) -> Optional[HistoryRecord]:
        """Aynı dosya parmak izine sahip başka bir TAMAMLANMIŞ kayıt var mı?"""
        if not fingerprint:
            return None
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM history WHERE status=? AND fingerprint=? AND id!=? ORDER BY downloaded_at DESC LIMIT 1",
                (STATUS_COMPLETED, fingerprint, exclude_id),
            )
            row = cur.fetchone()
            return self._row_to_record(row) if row else None

    def clear_errors(self) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM history WHERE status IN ('failed','cancelled')")

    def stale_downloads(self) -> list[HistoryRecord]:
        """Durumu hâlâ 'downloading' olan kayıtlar — uygulama çökmüş/kapanmış demektir
        (crash recovery, spec madde 39)."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM history WHERE status=? ORDER BY downloaded_at DESC", (STATUS_DOWNLOADING,))
            return [self._row_to_record(r) for r in cur.fetchall()]

    def stats(self) -> dict:
        """İstatistik ekranı için (spec madde 44)."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT media_type, COUNT(*), COALESCE(SUM(file_size),0) FROM history "
                "WHERE status=? GROUP BY media_type",
                (STATUS_COMPLETED,),
            )
            by_type = {r[0]: {"count": r[1], "bytes": r[2]} for r in cur.fetchall()}
            cur.execute(
                "SELECT platform, COUNT(*) FROM history WHERE status=? GROUP BY platform ORDER BY 2 DESC",
                (STATUS_COMPLETED,),
            )
            by_platform = {r[0] or "Diğer": r[1] for r in cur.fetchall()}
            total_files = sum(v["count"] for v in by_type.values())
            total_bytes = sum(v["bytes"] for v in by_type.values())
        return {"by_type": by_type, "by_platform": by_platform, "total_files": total_files, "total_bytes": total_bytes}

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
