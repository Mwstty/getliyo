"""getliyo — HTTP API + web arayüzü (FastAPI)."""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import shutil
import time
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.downloaders.base_downloader import MediaInfo
from app.downloaders.manager import DownloaderManager
from app.media.ffmpeg_manager import FFmpegManager
from app.utils.errors import UserError, error_key, friendly_message
from app.utils.logger import get_logger, setup_logging
from server import instagram, site
from server.config import Config
from server.jobs import DONE, Job, JobManager, QuotaError
from server.security import RateLimiter, assert_public_url, match_key, owner_id, sign_download, verify_download
from server.social import instagram as ig_mentions
from server.social import instagram_dm as ig_dm

log = get_logger("server")
WEB_DIR = Path(__file__).parent / "web"
WEB_DIST_DIR = Path(__file__).parent / "web-dist"  # scripts/build_web.py çıktısı: küçültülmüş/karartılmış üretim paketi
LINK_TTL = 15 * 60  # indirme bağlantısı geçerlilik süresi (sn)
TOKEN_EXT = (".html", ".txt", ".xml")  # {{SITE_URL}} bu dosyalarda gerçek adresle değiştirilir
VISITOR_ID = re.compile(r"^[A-Za-z0-9_-]{22,64}$")  # tarayıcının ürettiği rastgele kimlik
SAFE_HOST = re.compile(r"^[A-Za-z0-9.\-:\[\]]+$")


class SiteFiles(StaticFiles):
    """Statik site: {{SITE_URL}} yer tutucusunu doldurur, önbellek başlıklarını ayarlar.
    404 için klasördeki 404.html otomatik kullanılır."""

    def __init__(self, *, directory: Path, site_url: str = "") -> None:
        super().__init__(directory=directory, html=True)
        self.site_url = site_url

    def _base(self, scope) -> str:
        if self.site_url:
            return self.site_url
        headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "localhost")
        if not SAFE_HOST.match(host):
            host = "localhost"
        scheme = headers.get("x-forwarded-proto", scope.get("scheme", "http"))
        return f"{'https' if scheme == 'https' else 'http'}://{host}"

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        file_path = getattr(response, "path", "")
        if response.status_code == 200 and str(file_path).lower().endswith(TOKEN_EXT):
            text = Path(file_path).read_text(encoding="utf-8").replace("{{SITE_URL}}", self._base(scope))
            media = mimetypes.guess_type(str(file_path))[0] or "text/html"
            response = Response(text.encode("utf-8"), media_type=media)
            response.headers["Cache-Control"] = "no-cache"
        elif response.status_code == 200:
            long_lived = str(file_path).lower().endswith((".png", ".ico", ".svg", ".webp", ".jpg"))
            response.headers["Cache-Control"] = "public, max-age=86400" if long_lived else "no-cache"  # js/css: ETag ile doğrulanır
        return response


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=4, max_length=4096)


class JobRequest(BaseModel):
    url: str = Field(min_length=4, max_length=4096)
    preset: Literal["best", "best_mp4", "h1080", "h720", "audio"] = "best"
    entries: Optional[list[int]] = Field(default=None, max_length=100)
    format_id: Optional[str] = Field(default=None, max_length=200)


def info_to_dict(info: MediaInfo) -> dict:
    """MediaInfo -> JSON (küçük resim baytları ve indirme iç ayrıntıları dışarı verilmez)."""
    return {
        "url": info.source_url, "title": info.title, "platform": info.platform, "kind": info.kind,
        "uploader": info.uploader, "duration": info.duration, "thumbnail": info.thumbnail,
        "is_gallery": info.is_gallery, "requested_index": info.requested_index,
        "entries": [
            {
                "index": e.index, "title": e.title, "kind": e.kind, "duration": e.duration, "thumbnail": e.thumbnail,
                "formats": [
                    {"format_id": f.format_id, "kind": f.kind, "resolution": f.resolution, "container": f.container,
                     "codec": f.codec, "fps": f.fps, "filesize": f.filesize, "size_estimated": f.size_estimated}
                    for f in e.formats
                ],
            }
            for e in info.entries
        ],
    }


def create_app(config: Config | None = None, manager: DownloaderManager | None = None) -> FastAPI:
    config = config or Config.from_env()
    setup_logging()
    manager = manager or DownloaderManager(FFmpegManager())
    if config.proxy_url:
        manager.set_network(config.proxy_url, "")
    jobs = JobManager(config, manager)
    limiter = RateLimiter(config.analyze_per_minute)
    ip_limiter = RateLimiter(config.analyze_per_minute * 2)  # kimlik üretip kaçmaya karşı: IP başına

    dm: ig_dm.DmService | None = None
    _ig_env = {"GETLIYO_IG_APP_SECRET": config.instagram_app_secret, "GETLIYO_IG_VERIFY_TOKEN": config.instagram_verify_token,
               "GETLIYO_IG_PAGE_TOKEN": config.instagram_page_token, "GETLIYO_IG_BUSINESS_ID": config.instagram_business_id}
    if not config.instagram_enabled:  # yalnızca değişken ADLARI loglanır, değerleri asla
        missing = [k for k, v in _ig_env.items() if not v]
        if len(missing) < len(_ig_env):
            log.warning("Instagram entegrasyonu KAPALI; eksik ayarlar: %s", ", ".join(missing))
    elif not config.result_base_url:
        log.warning("Instagram DM yanıtları KAPALI; eksik ayar: GETLIYO_PUBLIC_BASE_URL (ya da GETLIYO_SITE_URL)")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if dm is not None:
            dm.start()
        yield
        if dm is not None:
            dm.stop()
        jobs.shutdown()

    app = FastAPI(
        title="getliyo API", version="1.0.0", lifespan=lifespan,
        docs_url="/api/docs" if config.enable_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if config.enable_docs else None,
    )
    app.state.jobs, app.state.config = jobs, config
    app.add_middleware(GZipMiddleware, minimum_size=500)  # site hızı: metin dosyaları ve JSON sıkıştırılır

    # Erişim kaydı: yalnızca zaman, IP, yöntem, yol (sorgu dizesi ve istek gövdesi YOK), durum. Süreye göre döner.
    access = logging.getLogger("getliyo.access")
    for old in list(access.handlers):  # yeniden kurulumda eski dosyaya bağlı kalma
        access.removeHandler(old)
        old.close()
    access.setLevel(logging.INFO)
    access.propagate = False
    try:
        logs = config.data_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(logs / "access.log", when="midnight", backupCount=config.log_retention_days, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        access.addHandler(handler)
    except OSError:
        access.addHandler(logging.NullHandler())

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/") or request.url.path in ("/", "/tr/", "/en/", "/ar/"):
            access.info("%s %s %s %s", client_ip(request), request.method, request.url.path, response.status_code)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if "text/html" in h.get("content-type", ""):
            h.setdefault("Content-Security-Policy", config.csp)
        return response

    if config.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(config.cors_origins), allow_methods=["GET", "POST", "DELETE"],
                           allow_headers=["Authorization", "X-API-Key", "Content-Type"])

    @app.exception_handler(UserError)
    async def user_error_handler(_req: Request, exc: UserError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.message, "code": exc.key})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_req: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "Geçersiz istek.", "code": "invalid_request"})

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "?"

    def authenticate(request: Request) -> str:
        if not config.auth_required:
            # Anahtarsız mod: her tarayıcı kendi rastgele kimliğini gönderir; liste/iş sahipliği buna göre ayrılır.
            visitor = request.headers.get("x-visitor-id", "")
            return owner_id("visitor:" + visitor) if VISITOR_ID.match(visitor) else owner_id("local")
        header = request.headers.get("authorization", "")
        candidate = header[7:].strip() if header.lower().startswith("bearer ") else request.headers.get("x-api-key", "")
        key = match_key(candidate, config.api_keys) if candidate else None
        if key is None:
            raise HTTPException(401, "Geçersiz ya da eksik API anahtarı.", headers={"WWW-Authenticate": "Bearer"})
        return owner_id(key)

    def job_to_dict(job: Job) -> dict:
        data = {
            "id": job.id, "url": job.url, "title": job.title, "platform": job.platform, "kind": job.kind,
            "label": job.label, "status": job.status, "percent": job.percent, "speed": job.speed, "eta": job.eta,
            "error": job.error, "error_code": job.error_code, "file_name": job.file_name, "file_size": job.file_size,
            "created_at": job.created_at, "finished_at": job.finished_at, "download_url": None,
        }
        if job.status == DONE:
            expires = int(time.time()) + LINK_TTL
            sig = sign_download(config.secret, job.id, expires)
            data["download_url"] = f"/api/jobs/{job.id}/file?exp={expires}&sig={sig}"
        return data

    def checked_url(raw: str) -> str:
        from app.utils.validators import validate_url

        url = validate_url(raw)
        instagram.check(url)
        host = (urlsplit(url).hostname or "").lower()
        if any(host == d or host.endswith("." + d) for d in config.blocked_domains):
            raise UserError("Bu kaynaktan indirme, hak sahibi talebiyle engellenmiştir.", "forbidden")
        assert_public_url(url, allow_private=config.allow_private_urls)
        return url

    # ------------------------------------------------------------------ API
    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/status")
    def status(_owner: str = Depends(authenticate)) -> dict:
        """Yönetici bilgisi (sürüm, disk). Yalnızca API anahtarı tanımlıyken ve doğru anahtarla erişilir."""
        if not config.auth_required:
            return {"status": "ok"}  # anahtarsız modda yönetici bilgisi (sürüm, disk) verilmez
        from yt_dlp.version import __version__ as ytdlp_version

        free = shutil.disk_usage(config.download_dir).free
        return {
            "ytdlp_version": ytdlp_version, "ffmpeg": manager.ffmpeg.is_available,
            "active_jobs": jobs.active_count(), "max_concurrent": config.max_concurrent,
            "disk_free_mb": free // (1024 * 1024), "retention_minutes": config.retention_minutes,
            "max_filesize_mb": config.max_filesize_mb,
        }

    @app.post("/api/analyze")
    def analyze(request: Request, req: AnalyzeRequest, owner: str = Depends(authenticate)) -> dict:
        if not (limiter.allow(owner) and ip_limiter.allow(client_ip(request))):
            raise HTTPException(429, "Çok fazla istek. Biraz bekleyip tekrar dene.")
        url = checked_url(req.url)
        try:
            return info_to_dict(manager.analyze(url))
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Analiz başarısız")
            raise UserError(friendly_message(exc), error_key(exc)) from exc

    @app.post("/api/jobs", status_code=201)
    def create_jobs(request: Request, req: JobRequest, owner: str = Depends(authenticate)) -> dict:
        if not (limiter.allow(owner) and ip_limiter.allow(client_ip(request))):
            raise HTTPException(429, "Çok fazla istek. Biraz bekleyip tekrar dene.")
        url = checked_url(req.url)
        try:
            info = manager.analyze(url)
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("Analiz başarısız")
            raise UserError(friendly_message(exc), error_key(exc)) from exc
        try:
            created = jobs.submit(owner, info, preset=req.preset, entries=req.entries, format_id=req.format_id)
        except QuotaError as exc:
            raise HTTPException(429, str(exc)) from exc
        return {"jobs": [job_to_dict(j) for j in created]}

    @app.get("/api/jobs")
    def list_jobs(owner: str = Depends(authenticate)) -> dict:
        return {"jobs": [job_to_dict(j) for j in jobs.list(owner)]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, owner: str = Depends(authenticate)) -> dict:
        job = jobs.get(job_id, owner)
        if job is None:
            raise HTTPException(404, "İş bulunamadı.")
        return job_to_dict(job)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    def delete_job(job_id: str, owner: str = Depends(authenticate)) -> None:
        """Çalışan işi iptal eder; biten işi ve dosyasını siler."""
        if not jobs.cancel_or_delete(job_id, owner):
            raise HTTPException(404, "İş bulunamadı.")

    @app.get("/api/jobs/{job_id}/file")
    def get_file(
        request: Request, job_id: str, exp: int = Query(0), sig: str = Query(""),
    ):
        """İmzalı bağlantı (tarayıcı indirmesi için) ya da API anahtarı ile dosyayı verir."""
        job = jobs.get(job_id)
        if job is not None and not verify_download(config.secret, job_id, exp, sig):
            owner = authenticate(request)  # imza yoksa/geçersizse anahtar şart
            job = jobs.get(job_id, owner)
        if job is None or job.status != DONE or not job.file_path:
            raise HTTPException(404, "Dosya bulunamadı.")
        path = Path(job.file_path).resolve()
        if not path.is_relative_to((config.download_dir / job.id).resolve()) or not path.is_file():
            raise HTTPException(404, "Dosya bulunamadı (süresi dolmuş olabilir).")
        return FileResponse(path, filename=job.file_name)

    # ------------------------------------------------------------------ Instagram mention -> DM (AŞAMA 6)
    if config.instagram_enabled:
        ig_client = ig_mentions.InstagramClient(config.instagram_page_token, config.instagram_business_id)

        def _build_download_link(job_id: str) -> str:
            expires = int(time.time()) + LINK_TTL
            sig = sign_download(config.secret, job_id, expires)
            return f"{config.site_url or ''}/api/jobs/{job_id}/file?exp={expires}&sig={sig}"

        def _run_mention(event: ig_mentions.MentionEvent) -> None:
            ig_mentions.process_mention(
                event, ig_client,
                analyze=manager.analyze,
                submit=lambda owner, info: jobs.submit(owner, info),
                get_job=lambda job_id: jobs.get(job_id),
                build_download_link=_build_download_link,
            )

        dm_limiter = RateLimiter(5)  # gönderen başına dakikada 5 mesaj; fazlası yanıtsız bırakılır
        if config.result_base_url:
            dm = ig_dm.DmService(
                client=ig_dm.DmClient(config.instagram_page_token, config.instagram_business_id),
                store=ig_dm.DmStore(config.data_dir / "ig_dm.db"),
                check_url=checked_url,
                analyze=manager.analyze,
                submit=lambda owner, info: jobs.submit(owner, info),
                get_job=lambda job_id: jobs.get(job_id),
                owner_for=lambda sender: owner_id("instagram-dm:" + sender),
                make_link=lambda job: f"{config.result_base_url}/r/" + ig_dm.result_token(
                    config.secret, job.id, int((job.finished_at or time.time()) + config.retention_minutes * 60)),
                allow=dm_limiter.allow,
            )

        @app.get("/webhooks/instagram", include_in_schema=False)
        def instagram_webhook_verify(
            hub_mode: str = Query("", alias="hub.mode"),
            hub_verify_token: str = Query("", alias="hub.verify_token"),
            hub_challenge: str = Query("", alias="hub.challenge"),
        ):
            result = ig_mentions.verify_subscription(
                config.instagram_verify_token, hub_mode, hub_verify_token, hub_challenge,
            )
            if result is None:
                raise HTTPException(403, "Doğrulama başarısız.")
            return PlainTextResponse(result)

        @app.post("/webhooks/instagram", include_in_schema=False)
        async def instagram_webhook_receive(request: Request, background: BackgroundTasks):
            body = await request.body()
            signature = request.headers.get("x-hub-signature-256")
            if not ig_mentions.verify_signature(config.instagram_app_secret, body, signature):
                raise HTTPException(403, "Geçersiz imza.")
            try:
                payload = json.loads(body)
            except Exception:
                raise HTTPException(400, "Geçersiz gövde.")
            if not isinstance(payload, dict):
                raise HTTPException(400, "Geçersiz gövde.")
            for event in ig_mentions.extract_mentions(payload):
                background.add_task(_run_mention, event)
            if dm is not None:
                for message in ig_dm.extract_messages(payload):
                    if dm.accept(message):  # yinelenen webhook olayı ikinci kez işe dönüşmez
                        background.add_task(dm.handle, message)
            return PlainTextResponse("ok")

    # ------------------------------------------------------------------ DM sonuç sayfası
    @app.get("/r/{token}", include_in_schema=False)
    def result_page(request: Request, token: str) -> HTMLResponse:
        """DM'deki süreli bağlantının açtığı sayfa: mevcut site çerçevesi + reklam alanları + indirme düğmesi."""
        h = request.headers
        lang = site.pick_lang(cookie=request.cookies.get(site.LANG_COOKIE, ""), country=h.get("cf-ipcountry", ""),
                              accept_language=h.get("accept-language", ""))
        job_id = ig_dm.parse_result_token(config.secret, token)
        job = jobs.get(job_id) if job_id else None
        path = Path(job.file_path).resolve() if job is not None and job.status == DONE and job.file_path else None
        if job is None or path is None or not path.is_relative_to((config.download_dir / job.id).resolve()) or not path.is_file():
            resp = page(site.render_result(lang, base_url(request)), status=410)
        else:
            expires = int(time.time()) + LINK_TTL
            sig = sign_download(config.secret, job.id, expires)
            resp = page(site.render_result(
                lang, base_url(request), file_name=job.file_name, file_size=job.file_size,
                download_url=f"/api/jobs/{job.id}/file?exp={expires}&sig={sig}"))
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    # ------------------------------------------------------------------ çok dilli sayfalar
    def base_url(request: Request) -> str:
        if config.site_url:
            return config.site_url
        host = request.headers.get("host", "localhost")
        if not SAFE_HOST.match(host):
            host = "localhost"
        scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
        return f"{'https' if scheme == 'https' else 'http'}://{host}"

    def page(html: str, status: int = 200) -> HTMLResponse:
        resp = HTMLResponse(html, status_code=status)
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/", include_in_schema=False)
    def root(request: Request):
        """Ziyaretçiyi dilinin sayfasına yönlendirir. Arama botları yönlendirilmez: İngilizce sayfayı görür."""
        h = request.headers
        if site.is_bot(h.get("user-agent", "")):
            resp = page(site.render_page("home", "en", base_url(request)))
            resp.headers["Vary"] = "User-Agent"
            return resp
        lang = site.pick_lang(
            cookie=request.cookies.get(site.LANG_COOKIE, ""),
            country=h.get("cf-ipcountry", ""),
            accept_language=h.get("accept-language", ""),
        )
        resp = RedirectResponse(f"/{lang}/", status_code=302)
        resp.headers["Vary"] = "Accept-Language, Cookie, CF-IPCountry, User-Agent"
        resp.headers["Cache-Control"] = "private, no-store"
        return resp

    def register_language(lang: str) -> None:
        @app.get(f"/{lang}/", include_in_schema=False, name=f"home_{lang}")
        def home(request: Request) -> HTMLResponse:
            return page(site.render_page("home", lang, base_url(request)))

        for slug in site.LEGAL_SLUGS:
            @app.get(f"/{lang}/{slug}", include_in_schema=False, name=f"{slug}_{lang}")
            def legal(request: Request, _lang: str = lang, _slug: str = slug) -> HTMLResponse:
                html = site.render_legal(_lang, _slug, base_url(request))
                if html is None:
                    raise HTTPException(404, "Not found")
                return page(html)

    for _lang in site.LANGS:
        register_language(_lang)

    def register_legacy(path: str, slug: str) -> None:
        @app.get(path, include_in_schema=False)
        def legacy() -> RedirectResponse:
            return RedirectResponse(f"/tr/{slug}", status_code=301)

    for _path, _slug in site.LEGACY_LEGAL.items():
        register_legacy(_path, _slug)

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap(request: Request) -> Response:
        resp = Response(site.sitemap_xml(base_url(request)), media_type="application/xml")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    app.state.dm = dm  # testler ve yönetim için (None = DM entegrasyonu kapalı)

    serve_dir = WEB_DIST_DIR if WEB_DIST_DIR.is_dir() and os.environ.get("GETLIYO_WEB_SOURCE") != "1" else WEB_DIR
    if serve_dir.is_dir():
        app.mount("/", SiteFiles(directory=serve_dir, site_url=config.site_url), name="web")
    return app
