"""DownloaderManager: gerçek yerel sunucudan indirme + doğrulama + (gerçek ffmpeg ile) dönüştürme."""
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image

from app.downloaders.base_downloader import (
    BACKEND_DIRECT, BACKEND_IMAGE, ConvertSpec, DownloadControl, DownloadTask, MediaFormat,
)
from app.downloaders.manager import DownloaderManager
from app.media.ffmpeg_manager import FFmpegManager
from app.utils.errors import UserError

FFMPEG = shutil.which("ffmpeg")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture
def web(tmp_path):
    root = tmp_path / "www"; root.mkdir()
    Image.new("RGB", (800, 600), (200, 30, 30)).save(root / "a.jpg")
    (root / "bos.mp4").write_bytes(b"")  # 0 bayt
    if FFMPEG:
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=15:duration=1",
                        "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264", "-c:a", "aac", str(root / "v.mp4")], check=True)
        (root / "bozuk.mp4").write_bytes(b"BU BIR VIDEO DEGIL" * 100)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(root)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def mgr():
    return DownloaderManager(FFmpegManager())


def _task(url, kind, out, name="dosya", container="jpg", backend=BACKEND_IMAGE, convert=None):
    fmt = MediaFormat("x", kind, container=container, backend=backend, url=url)
    return DownloadTask("t", url, fmt, out, name, convert=convert)


def test_image_download_verified(web, mgr, tmp_path):
    p = mgr.download(_task(f"{web}/a.jpg", "image", tmp_path), lambda i: None, DownloadControl())
    assert p.exists() and Image.open(p).size == (800, 600)


def test_zero_byte_download_rejected(web, mgr, tmp_path):
    with pytest.raises(UserError) as e:
        mgr.download(_task(f"{web}/bos.mp4", "video", tmp_path, container="mp4", backend=BACKEND_DIRECT), lambda i: None, DownloadControl())
    assert "doğrulanamadı" in e.value.message


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg yok")
def test_corrupt_video_rejected_by_ffprobe(web, mgr, tmp_path):
    if not mgr.ffmpeg.ffprobe_path:
        pytest.skip("ffprobe yok")
    with pytest.raises(UserError):
        mgr.download(_task(f"{web}/bozuk.mp4", "video", tmp_path, container="mp4", backend=BACKEND_DIRECT), lambda i: None, DownloadControl())


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg yok")
def test_download_then_convert_pipeline(web, mgr, tmp_path):
    t = _task(f"{web}/v.mp4", "video", tmp_path, "klip", "mp4", BACKEND_DIRECT, ConvertSpec("vp9", "webm", 180))
    t.fmt.needs_ffmpeg = True
    p = mgr.download(t, lambda i: None, DownloadControl())
    assert p.suffix == ".webm" and p.exists() and not (tmp_path / "klip.mp4").exists()
