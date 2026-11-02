from datetime import datetime, timezone

import pytest

from app.history.db import HistoryDB
from app.history.service import HistoryService, compute_fingerprint
from app.utils.filename import sanitize_filename
from app.utils.path_check import validate_download_dir


def now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def env(tmp_path):
    db = HistoryDB(tmp_path / "h.db")
    dl = tmp_path / "downloads"; dl.mkdir()
    appdir = tmp_path / "appdata"; appdir.mkdir()
    svc = HistoryService(db, protected_roots=[appdir])
    return db, svc, dl, appdir


def add_file(db, folder, name="a.mp4", content=b"hello world", status="completed"):
    f = folder / name
    f.write_bytes(content)
    rid = db.start(title=name, url=f"https://x/{name}", platform="X", media_type="video",
                   file_path=str(f), file_name=name, downloaded_at=now())
    db.mark_status(rid, status, file_size=len(content), file_path=str(f))
    return rid, f


def test_delete_from_history_keeps_file(env):
    db, svc, dl, _ = env
    rid, f = add_file(db, dl)
    svc.delete_from_history([rid])
    assert db.get(rid) is None and f.exists()  # dosyaya DOKUNULMADI


def test_single_delete_removes_file_and_record(env):
    db, svc, dl, _ = env
    rid, f = add_file(db, dl)
    ok, _ = svc.delete_file_and_record(rid, use_recycle_bin=False)
    assert ok and not f.exists() and db.get(rid) is None


def test_bulk_delete_only_recorded_files(env):
    db, svc, dl, _ = env
    rid, f = add_file(db, dl, "kayitli.mp4")
    stranger = dl / "kullanicinin_kendi_dosyasi.docx"; stranger.write_text("onemli")  # geçmişte YOK
    res = svc.delete_files_bulk([rid], use_recycle_bin=False)
    assert res.deleted == 1 and not f.exists()
    assert stranger.exists(), "geçmişte olmayan dosyaya ASLA dokunulmamalı"


def test_bulk_skips_modified_file(env):
    db, svc, dl, _ = env
    rid, f = add_file(db, dl, "a.mp4", b"orijinal")
    f.write_bytes(b"kullanici bunu degistirdi, boyut farkli")
    res = svc.delete_files_bulk([rid], use_recycle_bin=False)
    assert res.deleted == 0 and f.exists() and res.skipped and "değişmiş" in res.skipped[0][1]


def test_protected_root_not_deleted(env):
    db, svc, _, appdir = env
    rid, f = add_file(db, appdir, "settings_gibi.mp4")
    res = svc.delete_files_bulk([rid], use_recycle_bin=False)
    assert res.deleted == 0 and f.exists() and "korumalı" in res.skipped[0][1]
    ok, why = svc.delete_file_and_record(rid, False)
    assert not ok and f.exists()


def test_directory_never_deleted(env):
    db, svc, dl, _ = env
    d = dl / "klasor"; d.mkdir(); (d / "x.txt").write_text("x")
    rid = db.start(title="k", url="u", platform="", media_type="video", file_path=str(d), file_name="klasor", downloaded_at=now())
    db.mark_status(rid, "completed")
    res = svc.delete_files_bulk([rid], False)
    assert res.deleted == 0 and d.exists() and (d / "x.txt").exists()


def test_missing_file_record_cleaned_in_bulk(env):
    db, svc, dl, _ = env
    rid, f = add_file(db, dl); f.unlink()
    res = svc.delete_files_bulk([rid], False)
    assert res.deleted == 1 and db.get(rid) is None


def test_clear_history_keeps_all_files(env):
    db, svc, dl, _ = env
    _, f1 = add_file(db, dl, "1.mp4"); _, f2 = add_file(db, dl, "2.mp4")
    svc.clear_history()
    assert db.count() == 0 and f1.exists() and f2.exists()


def test_clear_history_and_files_touches_only_history_files(env):
    db, svc, dl, _ = env
    _, f1 = add_file(db, dl, "1.mp4")
    other = dl / "baska.txt"; other.write_text("x")
    res = svc.clear_history_and_files(use_recycle_bin=False)
    assert res.deleted == 1 and not f1.exists() and other.exists()


def test_file_status_and_relink(env, tmp_path):
    db, svc, dl, _ = env
    rid, f = add_file(db, dl)
    assert svc.file_status_text(db.get(rid)) == ""
    moved = tmp_path / "yeni_yer.mp4"; f.rename(moved)
    assert svc.file_status_text(db.get(rid)) == "Dosya bulunamadı"
    assert svc.relink(rid, moved) and svc.file_status_text(db.get(rid)) == ""
    assert not svc.relink(rid, tmp_path / "yok.mp4")


def test_duplicate_info(env):
    db, svc, dl, _ = env
    rid, f = add_file(db, dl, "a.mp4")
    d = svc.check_duplicate("https://x/a.mp4")
    assert d and d.file_exists
    f.unlink()
    assert not svc.check_duplicate("https://x/a.mp4").file_exists
    assert svc.check_duplicate("https://baska") is None


def test_fingerprint_stable_and_distinct(tmp_path):
    a = tmp_path / "a"; a.write_bytes(b"x" * 3_000_000)
    b = tmp_path / "b"; b.write_bytes(b"x" * 3_000_000)
    c = tmp_path / "c"; c.write_bytes(b"y" * 3_000_000)
    assert compute_fingerprint(a) == compute_fingerprint(b) != compute_fingerprint(c)
    assert compute_fingerprint(tmp_path / "yok") == ""


def test_executable_extension_spoof_neutralized():
    out = sanitize_filename("video.mp4.exe")
    assert not out.lower().endswith(".exe") and ".exe" not in out.lower().replace("_exe", "")
    assert sanitize_filename("normal video.mp4") == "normal video.mp4"
    assert sanitize_filename("..") == "indirilen_dosya"


def test_validate_download_dir(tmp_path):
    ok, _ = validate_download_dir(str(tmp_path / "yeni" / "alt"))
    assert ok and (tmp_path / "yeni" / "alt").is_dir()
    assert not validate_download_dir("")[0]
    assert not validate_download_dir("goreli/yol")[0]
    f = tmp_path / "dosya.txt"; f.write_text("x")
    assert not validate_download_dir(str(f))[0]
    assert validate_download_dir(str(tmp_path / "Türkçe Klasör ğüşiöç"))[0]


def test_stale_recovery_partials_and_discard(env):
    db, svc, dl, _ = env
    target = dl / "Yarim Video.mp4"
    rid = db.start(title="Yarim Video", url="https://y/1", platform="YouTube", media_type="video",
                   file_path=str(target), file_name=target.name, downloaded_at=now())
    (dl / "Yarim Video.mp4.part").write_bytes(b"xxx")
    (dl / "Yarim Video.f137.mp4.part").write_bytes(b"yyy")
    (dl / "Baska Video.mp4.part").write_bytes(b"zzz")  # başka indirmeye ait, DOKUNULMAMALI
    rec = db.stale_downloads()[0]
    assert len(svc.partial_files(rec)) == 2
    assert svc.discard_stale([rec]) == 1
    assert not list(dl.glob("Yarim*")) and (dl / "Baska Video.mp4.part").exists()
    assert db.get(rid).status == "cancelled" and db.stale_downloads() == []
