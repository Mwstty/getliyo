import os

import pytest

from app.utils import paths, secret
from app.utils.thumb_cache import ThumbCache
from app.utils.update_check import check_app_update, is_newer, parse_version
from app.utils.url_extract import clipboard_candidate, is_supported_url, parse_urls


# ---------------- url_extract
def test_parse_urls_multiple_lines_and_dedupe():
    text = "bak: https://youtu.be/abc, sonra\nhttps://x.com/u/status/1\nhttps://youtu.be/abc\nrastgele yazi"
    assert parse_urls(text) == ["https://youtu.be/abc", "https://x.com/u/status/1"]


def test_parse_urls_strips_trailing_punctuation_and_rejects_junk():
    assert parse_urls("(https://reddit.com/r/a/comments/1/x/).") == ["https://reddit.com/r/a/comments/1/x/"]
    assert parse_urls("file:///c:/x.exe javascript:alert(1)") == []


def test_supported_url_detection():
    assert is_supported_url("https://www.youtube.com/watch?v=x")
    assert is_supported_url("https://cdn.site.com/a.mp4")  # doğrudan medya
    assert not is_supported_url("https://www.rastgele-site.com/haber")
    assert not is_supported_url("bu bir url degil")


def test_clipboard_candidate_only_single_supported_url():
    assert clipboard_candidate("https://www.instagram.com/reel/abc/") == "https://www.instagram.com/reel/abc/"
    assert clipboard_candidate("  https://youtu.be/abc \n".strip()) == "https://youtu.be/abc"
    assert clipboard_candidate("sifrem: hunter2 https://youtu.be/abc") is None
    assert clipboard_candidate("https://youtu.be/a\nhttps://youtu.be/b") is None
    assert clipboard_candidate("x" * 5000) is None
    assert clipboard_candidate("https://www.rastgele-site.com/haber") is None
    assert clipboard_candidate("") is None


# ---------------- update_check
def test_version_compare():
    assert parse_version("v1.2.0") == (1, 2, 0)
    assert is_newer("v1.3.0", "1.2.0") and not is_newer("1.2.0", "1.2.0") and is_newer("1.2.1", "1.2")
    assert not is_newer("1.1.9", "1.2.0")


def test_update_check_variants():
    assert not check_app_update("", "1.2.0").ok
    info = check_app_update("a/b", "1.2.0", fetch=lambda u: {"tag_name": "v1.3.0", "html_url": "https://g/r"})
    assert info.ok and info.newer and info.latest == "1.3.0"
    same = check_app_update("a/b", "1.2.0", fetch=lambda u: {"tag_name": "v1.2.0"})
    assert same.ok and not same.newer
    def boom(u): raise OSError("net")
    assert not check_app_update("a/b", "1.2.0", fetch=boom).ok
    assert not check_app_update("a/b", "1.2.0", fetch=lambda u: {}).ok


# ---------------- thumb cache
def test_thumb_cache_hits_and_corruption(tmp_path):
    calls = []
    def fetch(url): calls.append(url); return b"IMGDATA"
    c = ThumbCache(tmp_path / "t", fetch)
    assert c.get("https://a/1.jpg") == b"IMGDATA" and c.get("https://a/1.jpg") == b"IMGDATA"
    assert len(calls) == 1, "aynı thumbnail tekrar indirilmemeli"
    (c._path("https://a/1.jpg")).write_bytes(b"")  # bozulmuş (boş) cache
    assert c.get("https://a/1.jpg") == b"IMGDATA"
    assert len(calls) == 2
    assert ThumbCache(tmp_path / "t2", lambda u: None).get("https://x") is None
    def bad(u): raise RuntimeError("x")
    assert ThumbCache(tmp_path / "t3", bad).get("https://x") is None  # istisna sızmaz
    assert c.clear() >= 1


# ---------------- secret
def test_secret_never_stores_plaintext_off_windows():
    if os.name == "nt":
        pytest.skip("DPAPI yalnızca Windows'ta; burada test edilemez")
    assert secret.protect("sifre123") == ""  # düz metin saklama YOK
    assert secret.unprotect("dpapi:abc") == ""
    assert not secret.available()


def test_redact_url():
    assert secret.redact_url("http://kullanici:parola@proxy.ornek.com:8080") == "http://proxy.ornek.com:8080"


# ---------------- portable
def test_portable_mode_uses_local_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path)
    assert not paths.is_portable()
    (tmp_path / "portable.flag").write_text("")
    assert paths.is_portable()
    assert paths.appdata_dir() == tmp_path / "data"
    assert paths.log_dir().parent == tmp_path / "data"
    assert paths.cache_dir().parent == tmp_path / "data"


def test_installed_mode_uses_appdata_env(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "app_dir", lambda: tmp_path / "Program Files" / "MIT")  # yazılamaz bir yer gibi
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    d = paths.appdata_dir()
    assert d == tmp_path / "Roaming" / paths.APP_NAME and "Program Files" not in str(d)


def test_read_urls_from_text_file(tmp_path):
    from app.ui.dialogs import read_urls_from_file
    f = tmp_path / "liste.txt"
    f.write_text("https://youtu.be/a\r\n\r\nnot: https://x.com/u/status/1\nhttps://youtu.be/a\n", encoding="utf-8")
    assert read_urls_from_file(str(f)) == ["https://youtu.be/a", "https://x.com/u/status/1"]
    tr = tmp_path / "tr.txt"
    tr.write_bytes("Şu video: https://youtu.be/b çok güzel".encode("cp1254"))
    assert read_urls_from_file(str(tr)) == ["https://youtu.be/b"]
    assert read_urls_from_file(str(tmp_path / "yok.txt")) == []
