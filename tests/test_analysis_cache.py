"""AnalysisCache: aynı URL'nin tekrar tekrar ağdan analiz edilmediğini GERÇEK bir sunucuya
karşı (istek sayarak) doğrular. Mock yok — spec'in 'gerçekten test et' kuralına uyar."""
from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.downloaders.analysis_cache import AnalysisCache
from app.downloaders.base_downloader import MediaEntry, MediaFormat, MediaInfo
from app.downloaders.manager import DownloaderManager
from app.media.ffmpeg_manager import FFmpegManager

VIDEO_BYTES = b"\x00" * 50_000


class CountingHandler(BaseHTTPRequestHandler):
    hits = 0
    lock = threading.Lock()

    def log_message(self, *a):  # sessiz
        pass

    def do_GET(self):
        with CountingHandler.lock:
            CountingHandler.hits += 1
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(VIDEO_BYTES)))
        self.end_headers()
        self.wfile.write(VIDEO_BYTES)


@pytest.fixture
def server():
    CountingHandler.hits = 0
    srv = ThreadingHTTPServer(("127.0.0.1", 0), CountingHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/video.mp4"
    srv.shutdown()


@pytest.fixture
def manager():
    return DownloaderManager(FFmpegManager())


def test_second_analyze_hits_zero_new_requests(server, manager):
    manager.analyze(server)
    hits_after_first = CountingHandler.hits
    assert hits_after_first >= 1
    manager.analyze(server)
    assert CountingHandler.hits == hits_after_first, "ikinci analiz cache'ten gelmeli, yeni istek atmamalı"


def test_force_refresh_bypasses_cache(server, manager):
    manager.analyze(server)
    hits_after_first = CountingHandler.hits
    manager.analyze(server, force_refresh=True)
    assert CountingHandler.hits > hits_after_first, "force_refresh ağdan tekrar çekmeli"


def test_tracking_param_variants_share_cache_entry(server, manager):
    manager.analyze(server)
    hits_after_first = CountingHandler.hits
    manager.analyze(server + "?utm_source=test&fbclid=abc")
    assert CountingHandler.hits == hits_after_first, "iz parametresi farkı aynı cache anahtarını paylaşmalı"


def test_ttl_expiry_causes_refetch(server, manager):
    manager.cache.ttl_seconds = 0.2
    manager.analyze(server)
    hits_after_first = CountingHandler.hits
    time.sleep(0.35)
    manager.analyze(server)
    assert CountingHandler.hits > hits_after_first, "TTL dolunca tekrar ağdan çekilmeli"


def test_cached_result_is_independent_copy(server, manager):
    info1 = manager.analyze(server)
    info1.thumbnail_bytes = b"MUTATED"
    info2 = manager.analyze(server)
    assert info2.thumbnail_bytes != b"MUTATED", "cache'teki orijinal, dışarıdaki mutasyondan korunmalı"


def _make_info(url: str) -> MediaInfo:
    fmt = MediaFormat(format_id="f1", kind="video", container="mp4", filesize=100, backend="direct", url=url)
    entry = MediaEntry(index=1, title="t", kind="video", formats=[fmt], url=url)
    return MediaInfo(source_url=url, title="t", platform="X", kind="video", entries=[entry])


def test_cache_get_set_invalidate_clear_len():
    cache = AnalysisCache(ttl_seconds=5)
    assert len(cache) == 0
    assert cache.get("k1") is None
    info = _make_info("https://example.com/a")
    cache.set("k1", info)
    assert len(cache) == 1
    got = cache.get("k1")
    assert got is not None and got.source_url == info.source_url
    cache.invalidate("k1")
    assert cache.get("k1") is None
    cache.set("k2", info)
    cache.clear()
    assert len(cache) == 0
