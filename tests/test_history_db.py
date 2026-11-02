from datetime import datetime, timedelta, timezone

import pytest

from app.history.db import HistoryDB
from app.history.models import STATUS_COMPLETED, STATUS_DOWNLOADING


def now_iso(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=offset_days)).isoformat()


@pytest.fixture
def db(tmp_path):
    return HistoryDB(tmp_path / "history.db")


def _add(db, title="V", url="https://x.com/1", platform="X", media_type="video",
         status=STATUS_COMPLETED, media_id="", downloaded_at=None, favorite=False):
    rid = db.start(
        title=title, url=url, platform=platform, media_type=media_type,
        file_path=f"/tmp/{title}.mp4", file_name=f"{title}.mp4",
        downloaded_at=downloaded_at or now_iso(), media_id=media_id,
    )
    db.mark_status(rid, status, file_size=1000, file_path=f"/tmp/{title}.mp4")
    if favorite:
        db.set_favorite(rid, True)
    return rid


def test_start_and_get(db):
    rid = db.start(title="T", url="https://y/1", platform="YouTube", media_type="video",
                   file_path="/x/T.mp4", file_name="T.mp4", downloaded_at=now_iso())
    rec = db.get(rid)
    assert rec.title == "T" and rec.status == STATUS_DOWNLOADING


def test_mark_completed_updates_size_and_path(db):
    rid = db.start(title="T", url="https://y/1", platform="YouTube", media_type="video",
                    file_path="", file_name="", downloaded_at=now_iso())
    db.mark_status(rid, STATUS_COMPLETED, file_size=555, file_path="/final/T.mp4")
    rec = db.get(rid)
    assert rec.status == STATUS_COMPLETED and rec.file_size == 555 and rec.file_path == "/final/T.mp4"


def test_delete_record_only_removes_db_row(db):
    rid = _add(db)
    assert db.get(rid) is not None
    db.delete_record(rid)
    assert db.get(rid) is None  # dosyaya dokunmadi, sadece kayit gitti (fiziksel silme baska katmanda)


def test_clear_all(db):
    _add(db); _add(db, title="V2")
    assert db.count() == 2
    db.clear_all()
    assert db.count() == 0


def test_filters_search_platform_media_type(db):
    _add(db, title="Kedi videosu", platform="YouTube", media_type="video")
    _add(db, title="Kopek fotosu", platform="Instagram", media_type="image")
    assert db.count(search="Kedi") == 1
    assert db.count(platform="Instagram") == 1
    assert db.count(media_type="image") == 1
    assert db.count(platform="Reddit") == 0


def test_favorites_filter(db):
    _add(db, title="A", favorite=True)
    _add(db, title="B", favorite=False)
    favs = db.list(favorites_only=True)
    assert len(favs) == 1 and favs[0].title == "A"


def test_since_filter(db):
    _add(db, title="Eski", downloaded_at=now_iso(40))
    _add(db, title="Yeni", downloaded_at=now_iso(0))
    recent = db.list(since_iso=now_iso(7))
    assert [r.title for r in recent] == ["Yeni"]


def test_pagination_order_newest_first(db):
    for i in range(5):
        _add(db, title=f"item{i}", downloaded_at=now_iso(5 - i))
    page1 = db.list(limit=2, offset=0)
    page2 = db.list(limit=2, offset=2)
    assert [r.title for r in page1] == ["item4", "item3"]
    assert [r.title for r in page2] == ["item2", "item1"]


def test_duplicate_detection_by_url(db):
    _add(db, url="https://x.com/1/status/1", media_id="")
    dup = db.find_duplicate("https://x.com/1/status/1")
    assert dup is not None
    assert db.find_duplicate("https://x.com/1/status/2") is None


def test_duplicate_detection_ignores_failed(db):
    _add(db, url="https://x.com/1", status="failed")
    assert db.find_duplicate("https://x.com/1") is None


def test_duplicate_detection_by_media_id(db):
    _add(db, url="https://youtube.com/watch?v=abc", media_id="abc123")
    dup = db.find_duplicate("https://youtube.com/watch?v=abc&t=5", media_id="abc123")
    assert dup is not None


def test_stale_downloads_for_crash_recovery(db):
    db.start(title="Yarim", url="https://y/1", platform="YouTube", media_type="video",
              file_path="", file_name="", downloaded_at=now_iso())
    _add(db, title="Tamam")
    stale = db.stale_downloads()
    assert len(stale) == 1 and stale[0].title == "Yarim"


def test_platforms_distinct(db):
    _add(db, platform="YouTube"); _add(db, platform="YouTube"); _add(db, platform="Instagram")
    assert sorted(db.platforms()) == ["Instagram", "YouTube"]


def test_stats(db):
    _add(db, media_type="video", platform="YouTube")
    _add(db, media_type="image", platform="Instagram")
    _add(db, media_type="video", platform="YouTube", status="failed")  # sayilmamali
    s = db.stats()
    assert s["total_files"] == 2
    assert s["by_type"]["video"]["count"] == 1
    assert s["by_platform"]["YouTube"] == 1


def test_favorite_toggle(db):
    rid = _add(db, favorite=False)
    db.set_favorite(rid, True)
    assert db.get(rid).is_favorite is True
    db.set_favorite(rid, False)
    assert db.get(rid).is_favorite is False


def test_update_path_for_moved_file(db):
    rid = _add(db)
    db.update_path(rid, "/new/location/video.mp4")
    rec = db.get(rid)
    assert rec.file_path == "/new/location/video.mp4" and rec.file_name == "video.mp4"


def test_reopen_db_preserves_data(tmp_path):
    path = tmp_path / "h.db"
    db1 = HistoryDB(path)
    _add(db1, title="Kalici")
    db1.close()
    db2 = HistoryDB(path)
    assert db2.count() == 1
    assert db2.list()[0].title == "Kalici"


def test_bulk_delete(db):
    ids = [_add(db, title=f"x{i}") for i in range(4)]
    db.delete_records(ids[:2])
    assert db.count() == 2


def test_migration_v1_to_v2_preserves_records(tmp_path):
    """Eski (v1) bir veritabanı kullanıcı kayıtları KAYBOLMADAN v2'ye yükseltilmeli."""
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '', media_type TEXT NOT NULL DEFAULT '', file_path TEXT NOT NULL DEFAULT '',
            file_name TEXT NOT NULL DEFAULT '', file_size INTEGER, resolution TEXT NOT NULL DEFAULT '',
            thumbnail TEXT NOT NULL DEFAULT '', downloaded_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'completed',
            duration REAL, is_favorite INTEGER NOT NULL DEFAULT 0, media_id TEXT NOT NULL DEFAULT '',
            format_container TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO history (title, url, platform, media_type, downloaded_at, is_favorite)
        VALUES ('Eski Kayit', 'https://y/1', 'YouTube', 'video', '2026-01-01T00:00:00+00:00', 1);
        PRAGMA user_version = 1;
    """)
    conn.commit(); conn.close()

    db = HistoryDB(path)
    recs = db.list()
    assert len(recs) == 1 and recs[0].title == "Eski Kayit" and recs[0].is_favorite
    assert recs[0].error_message == "" and recs[0].fingerprint == ""
    db.mark_status(recs[0].id, "failed", error_message="Sebep")
    assert db.get(recs[0].id).error_message == "Sebep"
    db.close()
    assert HistoryDB(path).count() == 1  # ikinci açılışta tekrar migrate etmemeli / bozulmamalı


def test_status_filter_and_errors(db):
    _add(db, title="ok")
    rid = _add(db, title="bad", status="failed")
    db.mark_status(rid, "failed", error_message="Erişilemedi")
    assert db.count(statuses=("failed",)) == 1
    assert db.list(statuses=("failed",))[0].error_message == "Erişilemedi"
    assert db.count(statuses=("completed",)) == 1
    db.clear_errors()
    assert db.count() == 1


def test_fingerprint_lookup(db):
    a = _add(db, title="a"); b = _add(db, title="b")
    db.mark_status(a, "completed", fingerprint="abc")
    db.mark_status(b, "completed", fingerprint="abc")
    assert db.find_by_fingerprint("abc", exclude_id=b).id == a
    assert db.find_by_fingerprint("", exclude_id=0) is None
