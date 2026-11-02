import httpx
import pytest

from app.downloaders import http_utils
from app.utils.errors import UserError
from app.utils.net_guard import guard_request, set_public_only
from server.config import Config
from server.security import RateLimiter


@pytest.fixture(autouse=True)
def _reset():
    yield
    set_public_only(False)
    http_utils.set_max_download_bytes(0)


def _client(handler):
    return httpx.Client(follow_redirects=True, transport=httpx.MockTransport(handler),
                        event_hooks={"request": [guard_request]})


def test_guard_kapaliyken_localhost_serbest():
    with _client(lambda r: httpx.Response(200)) as c:
        assert c.get("http://127.0.0.1/x").status_code == 200


def test_guard_aciksa_dogrudan_localhost_engellenir():
    set_public_only(True)
    with _client(lambda r: httpx.Response(200)) as c, pytest.raises(UserError):
        c.get("http://127.0.0.1/x")


def test_guard_aciksa_yonlendirme_ic_agi_engeller():
    set_public_only(True)

    def handler(request):
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})
        return httpx.Response(200)

    with _client(handler) as c, pytest.raises(UserError):
        c.get("http://93.184.216.34/")


def test_make_client_guard_kancasi_var():
    with http_utils.make_client() as c:
        assert guard_request in c.event_hooks["request"]


def test_ratelimiter_eski_anahtarlari_temizler(monkeypatch):
    rl = RateLimiter(1000)
    t = [1000.0]
    monkeypatch.setattr("server.security.time.monotonic", lambda: t[0])
    for i in range(200):
        assert rl.allow(f"ip{i}")
    t[0] += 120
    for i in range(200, 460):  # 256. çağrıda temizlik tetiklenir
        rl.allow(f"yeni{i}")
    assert len(rl._hits) < 400


def test_outtmpl_yuzde_kacirilir(tmp_path):
    from app.downloaders.base_downloader import DownloadTask, MediaFormat
    from app.downloaders.ytdlp_downloader import build_download_opts

    fmt = MediaFormat(format_id="best", kind="video")
    task = DownloadTask(title="t", url="https://x", fmt=fmt, out_dir=tmp_path, base_name="a")
    opts = build_download_opts({}, task, "Baslik %(title)s %d")
    assert "%%(title)s" in opts["outtmpl"]["default"]
    assert opts["outtmpl"]["default"].endswith(".%(ext)s")


def test_config_varsayilan_boyut_siniri_ve_gecersiz_float(monkeypatch, tmp_path):
    monkeypatch.setenv("GETLIYO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GETLIYO_MAX_FILESIZE_MB", raising=False)
    monkeypatch.setenv("GETLIYO_RATE_LIMIT_MBPS", "abc")
    cfg = Config.from_env()
    assert cfg.max_filesize_mb == 2000
    assert cfg.rate_limit_mbps == 0.0


def test_saklama_suresi_ust_siniri_15_dakika(monkeypatch, tmp_path):
    monkeypatch.setenv("GETLIYO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GETLIYO_RETENTION_MINUTES", "600")
    assert Config.from_env().retention_minutes == 15
    monkeypatch.delenv("GETLIYO_RETENTION_MINUTES")
    assert Config.from_env().retention_minutes == 15


def test_cozumleme_korumasi_ic_adresleri_reddeder():
    import socket
    from app.utils.net_guard import allow_host, install_resolver_guard

    install_resolver_guard()
    set_public_only(True)
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("localhost", 80)
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("127.0.0.1", 80)
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("::ffff:127.0.0.1", 80)
    # sunucunun kendi dinleme adresi (AI_PASSIVE) etkilenmez
    assert socket.getaddrinfo("127.0.0.1", 80, flags=socket.AI_PASSIVE)
    # açıkça izin verilen host (ör. proxy)
    allow_host("localhost")
    assert socket.getaddrinfo("localhost", 80)
    set_public_only(False)
    assert socket.getaddrinfo("127.0.0.1", 80)
