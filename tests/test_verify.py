from PIL import Image

from app.utils.verify import verify_download


def test_missing(tmp_path):
    assert not verify_download(tmp_path / "yok.mp4", "video")


def test_empty(tmp_path):
    f = tmp_path / "a.mp4"; f.write_bytes(b"")
    r = verify_download(f, "video")
    assert not r and "boş" in r.reason


def test_valid_image(tmp_path):
    f = tmp_path / "a.png"; Image.new("RGB", (10, 10)).save(f)
    assert verify_download(f, "image")


def test_corrupt_image(tmp_path):
    f = tmp_path / "a.jpg"; f.write_bytes(b"bu bir resim degil")
    assert not verify_download(f, "image")


def test_video_without_ffprobe_passes_basic_checks(tmp_path):
    f = tmp_path / "a.mp4"; f.write_bytes(b"x" * 100)
    assert verify_download(f, "video", ffprobe=None)
