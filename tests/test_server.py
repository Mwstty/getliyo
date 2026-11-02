import time

import pytest
from fastapi.testclient import TestClient

from app.downloaders.base_downloader import KIND_VIDEO, MediaEntry, MediaFormat, MediaInfo
from app.utils.errors import CancelledError
from server.app import create_app
from server.config import Config
from server.security import RateLimiter, assert_public_url, sign_download, verify_download
from app.utils.errors import UserError

KEY = "test-key"
AUTH = {"Authorization": f"Bearer {KEY}"}


class FakeFfmpeg:
    is_available = True


class FakeManager:
    ffmpeg = FakeFfmpeg()

    def __init__(self):
        self.fail = False
        self.slow = False

    def set_network(self, *_a):
        pass

    def analyze(self, url):
        fmts = [
            MediaFormat("v1080", KIND_VIDEO, "1080p", height=1080, container="mp4", filesize=1000),
            MediaFormat("v720", KIND_VIDEO, "720p", height=720, container="mp4", filesize=500),
        ]
        entry = MediaEntry(1, "Test Video", KIND_VIDEO, fmts, media_id="abc", url=url)
        return MediaInfo(source_url=url, title="Test Video", platform="Test", kind=KIND_VIDEO, entries=[entry])

    def download(self, task, progress, control):
        if self.fail:
            raise RuntimeError("boom")
        task.out_dir.mkdir(parents=True, exist_ok=True)
        for _ in range(50 if self.slow else 1):
            if control.is_set():
                raise CancelledError()
            time.sleep(0.05 if self.slow else 0)
        path = task.out_dir / f"{task.base_name}.{task.fmt.container}"
        path.write_bytes(b"data")
        return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    cfg = Config(
        data_dir=tmp_path, download_dir=tmp_path / "dl", api_keys=frozenset({KEY}), secret=b"s" * 32,
        allow_private_urls=True, max_active_per_key=2,
    )
    (tmp_path / "dl").mkdir()
    fake = FakeManager()
    app = create_app(cfg, fake)
    with TestClient(app) as client:
        yield client, fake, cfg


def wait_done(client, job_id, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}", headers=AUTH).json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("iş zamanında bitmedi")


def test_auth_required(env):
    client, _, _ = env
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/jobs").status_code == 401
    assert client.get("/api/jobs", headers={"Authorization": "Bearer yanlis"}).status_code == 401
    assert client.get("/api/jobs", headers={"X-API-Key": KEY}).status_code == 200


def test_analyze(env):
    client, _, _ = env
    r = client.post("/api/analyze", json={"url": "https://example.com/v"}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Test Video" and len(body["entries"][0]["formats"]) == 2
    assert "thumbnail_bytes" not in body


def test_invalid_url_is_422(env):
    client, _, _ = env
    r = client.post("/api/analyze", json={"url": "ftp://x"}, headers=AUTH)
    assert r.status_code == 422 and r.json()["code"] == "invalid_url"


def test_job_lifecycle_and_download(env):
    client, _, _ = env
    r = client.post("/api/jobs", json={"url": "https://example.com/v", "preset": "h720"}, headers=AUTH)
    assert r.status_code == 201
    job = wait_done(client, r.json()["jobs"][0]["id"])
    assert job["status"] == "done" and job["file_name"].endswith(".mp4")
    # imzalı bağlantı anahtarsız çalışır
    f = client.get(job["download_url"])
    assert f.status_code == 200 and f.content == b"data"
    # imzasız ve anahtarsız erişim reddedilir
    assert client.get(f"/api/jobs/{job['id']}/file").status_code == 401
    # sahibi silince dosya ve kayıt gider
    assert client.delete(f"/api/jobs/{job['id']}", headers=AUTH).status_code == 204
    assert client.get(f"/api/jobs/{job['id']}", headers=AUTH).status_code == 404


def test_failed_job_reports_friendly_error(env):
    client, fake, _ = env
    fake.fail = True
    r = client.post("/api/jobs", json={"url": "https://example.com/v"}, headers=AUTH)
    job = wait_done(client, r.json()["jobs"][0]["id"])
    assert job["status"] == "failed" and job["error"]
    assert "boom" not in job["error"]


def test_cancel_running_job(env):
    client, fake, _ = env
    fake.slow = True
    job_id = client.post("/api/jobs", json={"url": "https://example.com/v"}, headers=AUTH).json()["jobs"][0]["id"]
    assert client.delete(f"/api/jobs/{job_id}", headers=AUTH).status_code == 204
    assert wait_done(client, job_id)["status"] == "cancelled"


def test_quota(env):
    client, fake, _ = env
    fake.slow = True
    for _ in range(2):
        assert client.post("/api/jobs", json={"url": "https://example.com/v"}, headers=AUTH).status_code == 201
    assert client.post("/api/jobs", json={"url": "https://example.com/v"}, headers=AUTH).status_code == 429


def test_unknown_format_rejected(env):
    client, _, _ = env
    r = client.post("/api/jobs", json={"url": "https://example.com/v", "format_id": "yok"}, headers=AUTH)
    assert r.status_code == 422


def test_signature_and_expiry():
    sig = sign_download(b"k", "job", 4_000_000_000)
    assert verify_download(b"k", "job", 4_000_000_000, sig)
    assert not verify_download(b"k", "other", 4_000_000_000, sig)
    assert not verify_download(b"k", "job", 1, sign_download(b"k", "job", 1))  # süresi geçmiş


def test_ssrf_blocks_private():
    for url in ("http://127.0.0.1/x", "http://169.254.169.254/latest", "http://10.0.0.5/a", "http://localhost/a"):
        with pytest.raises(UserError):
            assert_public_url(url)


def test_rate_limiter():
    rl = RateLimiter(2)
    assert rl.allow("a") and rl.allow("a") and not rl.allow("a") and rl.allow("b")


def test_web_ui_served(env):
    client, _, _ = env
    r = client.get("/")
    assert r.status_code == 200 and "getliyo" in r.text


def test_open_mode_without_keys(tmp_path):
    cfg = Config(data_dir=tmp_path, download_dir=tmp_path / "dl", api_keys=frozenset(), secret=b"s" * 32,
                 allow_private_urls=True)
    (tmp_path / "dl").mkdir()
    with TestClient(create_app(cfg, FakeManager())) as client:
        assert client.get("/api/jobs").status_code == 200
        assert client.post("/api/analyze", json={"url": "https://example.com/v"}).status_code == 200


def test_blocked_domain(tmp_path):
    cfg = Config(data_dir=tmp_path, download_dir=tmp_path / "dl", api_keys=frozenset(), secret=b"s" * 32,
                 allow_private_urls=True, blocked_domains=("engelli.com",))
    (tmp_path / "dl").mkdir()
    with TestClient(create_app(cfg, FakeManager())) as client:
        r = client.post("/api/analyze", json={"url": "https://www.engelli.com/v"})
        assert r.status_code == 422 and r.json()["code"] == "forbidden"
        assert client.post("/api/analyze", json={"url": "https://iyi.com/v"}).status_code == 200


def test_visitors_are_isolated_in_open_mode(tmp_path):
    cfg = Config(data_dir=tmp_path, download_dir=tmp_path / "dl", api_keys=frozenset(), secret=b"s" * 32, allow_private_urls=True)
    (tmp_path / "dl").mkdir()
    a = {"X-Visitor-Id": "A" * 32}
    b = {"X-Visitor-Id": "B" * 32}
    with TestClient(create_app(cfg, FakeManager())) as client:
        job = client.post("/api/jobs", json={"url": "https://example.com/v"}, headers=a).json()["jobs"][0]["id"]
        assert len(client.get("/api/jobs", headers=a).json()["jobs"]) == 1
        assert client.get("/api/jobs", headers=b).json()["jobs"] == []
        assert client.get(f"/api/jobs/{job}", headers=b).status_code == 404
        assert client.delete(f"/api/jobs/{job}", headers=b).status_code == 404


def test_docs_and_status_closed_by_default(env):
    client, _, _ = env
    for path in ("/api/docs", "/api/openapi.json"):
        assert client.get(path).status_code == 404
    assert client.get("/api/status").status_code == 401  # anahtarsız erişim yok


def test_status_gives_no_details_in_open_mode(tmp_path):
    cfg = Config(data_dir=tmp_path, download_dir=tmp_path / "dl", api_keys=frozenset(), secret=b"s" * 32)
    (tmp_path / "dl").mkdir()
    with TestClient(create_app(cfg, FakeManager())) as client:
        body = client.get("/api/status").json()
        assert body == {"status": "ok"}


def test_validation_error_does_not_echo_input(env):
    client, _, _ = env
    r = client.post("/api/jobs", json={"url": 123}, headers=AUTH)
    assert r.status_code == 422 and "123" not in r.text and "input" not in r.json()


def test_security_headers(env):
    client, _, _ = env
    r = client.get("/")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY" and "permissions-policy" in r.headers


def test_access_log_has_no_query_or_body(env, tmp_path):
    client, _, cfg = env
    client.post("/api/analyze", json={"url": "https://example.com/gizli-yol?token=abc"}, headers=AUTH)
    import logging
    for h in logging.getLogger("getliyo.access").handlers:
        h.flush()
    text = (cfg.data_dir / "logs" / "access.log").read_text(encoding="utf-8")
    assert "POST /api/analyze 200" in text and "gizli-yol" not in text and "token" not in text


def test_expired_jobs_are_purged_after_15_minutes(env):
    client, _, cfg = env
    assert cfg.retention_minutes == 15
    old = client.post("/api/jobs", json={"url": "https://example.com/a"}, headers=AUTH).json()["jobs"][0]["id"]
    recent = client.post("/api/jobs", json={"url": "https://example.com/b"}, headers=AUTH).json()["jobs"][0]["id"]
    wait_done(client, old); wait_done(client, recent)
    jobs = client.app.state.jobs
    jobs.get(old).finished_at = time.time() - 16 * 60   # 16 dakika önce bitti
    jobs.get(recent).finished_at = time.time() - 10 * 60  # 10 dakika önce
    assert jobs.purge_expired() == 1
    assert client.get(f"/api/jobs/{old}", headers=AUTH).status_code == 404
    assert client.get(f"/api/jobs/{recent}", headers=AUTH).status_code == 200
    assert not (cfg.download_dir / old).exists()
