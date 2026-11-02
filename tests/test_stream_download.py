"""stream_download: gerçek yerel HTTP sunucusuna karşı pause/resume, retry, iptal, hız limiti."""
import hashlib
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.downloaders.base_downloader import DownloadControl
from app.downloaders.http_utils import stream_download
from app.utils.errors import CancelledError

DATA = os.urandom(600_000)  # 600 KB rastgele içerik
SHA = hashlib.sha256(DATA).hexdigest()


class Handler(BaseHTTPRequestHandler):
    fail_first = 0          # ilk N istekte yarıda kes
    slow = False            # yavaş gönder (pause/iptal testi için)
    calls: list = []
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # sessiz
        pass

    def do_GET(self):
        Handler.calls.append(self.headers.get("Range"))
        start = 0
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            start = int(rng[6:].split("-")[0])
        body = DATA[start:]
        if rng:
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(DATA)-1}/{len(DATA)}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        sent = 0
        cut = len(body) // 2 if Handler.fail_first > 0 else None
        if Handler.fail_first > 0:
            Handler.fail_first -= 1
        while sent < len(body):
            end = min(sent + 20_000, len(body))
            if cut is not None and sent >= cut:
                try:
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)  # gerçekten kes
                except OSError:
                    pass
                self.close_connection = True
                return
            try:
                self.wfile.write(body[sent:end])
            except (BrokenPipeError, ConnectionResetError):
                return
            sent = end
            if Handler.slow:
                time.sleep(0.05)


@pytest.fixture
def server():
    Handler.fail_first = 0
    Handler.slow = False
    Handler.calls = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/file.bin"
    srv.shutdown()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_plain_download(server, tmp_path):
    out = stream_download(server, tmp_path, "dosya", "bin", "new", lambda p: None, DownloadControl())
    assert _sha(out) == SHA


def test_auto_retry_resumes_with_range(server, tmp_path):
    Handler.fail_first = 1  # ilk bağlantı yarıda kopacak
    events = []
    out = stream_download(
        server, tmp_path, "dosya", "bin", "new", events.append, DownloadControl(),
        max_retries=3, backoff_start=3, sleep=lambda s: None,
    )
    assert _sha(out) == SHA  # dosya bozulmadan tamamlandı
    assert any(c and c.startswith("bytes=") for c in Handler.calls), "retry Range ile devam etmeliydi"
    assert any("Bağlantı koptu" in (e.status or "") for e in events)


def test_retry_gives_up_after_max(server, tmp_path):
    import httpx
    Handler.fail_first = 99
    with pytest.raises(httpx.TransportError):
        stream_download(server, tmp_path, "d", "bin", "new", lambda p: None, DownloadControl(),
                        max_retries=1, sleep=lambda s: None)


def test_pause_keeps_partial_then_resume_completes(server, tmp_path):
    Handler.slow = True
    control = DownloadControl()
    box = {}

    def run():
        try:
            stream_download(server, tmp_path, "dosya", "bin", "new", lambda p: None, control)
        except CancelledError:
            box["paused"] = True

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.4)
    control.stop(keep_partial=True)  # DURAKLAT
    t.join(5)
    assert box.get("paused")
    part = tmp_path / "dosya.bin.part"
    assert part.exists() and 0 < part.stat().st_size < len(DATA), "yarım dosya korunmalı"

    Handler.slow = False
    Handler.calls.clear()
    out = stream_download(server, tmp_path, "dosya", "bin", "overwrite", lambda p: None, DownloadControl())
    assert _sha(out) == SHA
    assert Handler.calls and Handler.calls[0].startswith("bytes="), "DEVAM ET Range ile kaldığı yerden sürmeli"


def test_cancel_deletes_partial(server, tmp_path):
    Handler.slow = True
    control = DownloadControl()

    def run():
        try:
            stream_download(server, tmp_path, "dosya", "bin", "new", lambda p: None, control)
        except CancelledError:
            pass

    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.4)
    control.stop(keep_partial=False)  # İPTAL
    t.join(5)
    assert not list(tmp_path.glob("*.part")), "iptalde yarım dosya silinmeli"
    assert not (tmp_path / "dosya.bin").exists()


def test_rate_limit_slows_download(server, tmp_path):
    start = time.monotonic()
    out = stream_download(server, tmp_path, "d", "bin", "new", lambda p: None, DownloadControl(),
                          rate_limit_bps=300_000)  # 300 KB/s -> 600 KB ≈ 2 sn
    elapsed = time.monotonic() - start
    assert _sha(out) == SHA
    assert elapsed >= 1.4, f"hız limiti etkisiz: {elapsed:.2f}s"
