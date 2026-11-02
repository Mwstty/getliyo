from datetime import datetime, timezone

from app.utils import uninstall_cleanup


def now():
    return datetime.now(timezone.utc).isoformat()


def test_downloads_cleanup_only_removes_recorded_files(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"; appdata.mkdir()
    downloads = tmp_path / "downloads"; downloads.mkdir()
    monkeypatch.setattr(uninstall_cleanup, "appdata_dir", lambda: appdata)
    from app.history.db import HistoryDB

    db = HistoryDB(appdata / "history.db")
    f = downloads / "video.mp4"; f.write_bytes(b"1234")
    rid = db.start(title="v", url="u", platform="", media_type="video", file_path=str(f),
                    file_name="video.mp4", downloaded_at=now())
    db.mark_status(rid, "completed", file_size=4, file_path=str(f))
    stranger = downloads / "kullanicinin_dosyasi.txt"; stranger.write_text("dokunma")
    db.close()

    uninstall_cleanup.run_cleanup(["--downloads"])
    assert not f.exists() and stranger.exists()


def test_settings_history_cache_logs_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(uninstall_cleanup, "appdata_dir", lambda: tmp_path)
    (tmp_path / "settings.json").write_text("{}")
    (tmp_path / "history.db").write_text("x")
    (tmp_path / "cache").mkdir(); (tmp_path / "cache" / "a.img").write_bytes(b"x")
    (tmp_path / "logs").mkdir(); (tmp_path / "logs" / "app.log").write_text("x")

    uninstall_cleanup.run_cleanup(["--settings", "--history", "--cache", "--logs"])
    assert not (tmp_path / "settings.json").exists()
    assert not (tmp_path / "history.db").exists()
    assert not (tmp_path / "cache").exists()
    assert not (tmp_path / "logs").exists()


def test_no_flags_deletes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(uninstall_cleanup, "appdata_dir", lambda: tmp_path)
    (tmp_path / "settings.json").write_text("{}")
    uninstall_cleanup.run_cleanup([])
    assert (tmp_path / "settings.json").exists()
