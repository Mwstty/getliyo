from pathlib import Path

from app.utils.trash import delete_file, permanently_delete


def test_permanently_delete_file(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert permanently_delete(f) is True
    assert not f.exists()


def test_permanently_delete_missing_is_true(tmp_path):
    # var olmayan dosya icin delete_file "zaten yok" mantigiyla True donmeli
    assert delete_file(tmp_path / "yok.txt") is True


def test_delete_file_non_windows_falls_back_to_permanent(tmp_path, monkeypatch):
    f = tmp_path / "b.txt"
    f.write_text("x")
    monkeypatch.setattr("os.name", "posix")
    assert delete_file(f, use_recycle_bin=True) is True
    assert not f.exists()


def test_permanently_delete_dir(tmp_path):
    d = tmp_path / "klasor"
    d.mkdir()
    (d / "ic.txt").write_text("x")
    assert permanently_delete(d) is True
    assert not d.exists()
