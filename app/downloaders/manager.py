"""Doğru adaptörü seçer: URL analizi ve indirme yönlendirmesi."""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlsplit

from app.downloaders.analysis_cache import AnalysisCache
from app.downloaders.base_downloader import (
    KIND_IMAGE,
    BACKEND_DIRECT,
    BACKEND_IMAGE,
    BACKEND_YTDLP,
    KIND_VIDEO,
    DownloadControl,
    DownloadTask,
    MediaInfo,
    ProgressCallback,
)
from app.downloaders.direct_downloader import DirectDownloader, _entry_from_av
from app.downloaders.http_utils import fetch_thumbnail, make_client, sniff
from app.downloaders.image_downloader import ImageDownloader, best_image_entry
from app.downloaders.platform_detector import detect_platform, resolve_url
from app.downloaders.ytdlp_downloader import YtdlpDownloader
from app.media.convert import convert_file
from app.media.ffmpeg_manager import FFmpegManager
from app.platforms import instagram, tiktok, twitter
from app.utils.errors import NoMediaError, UserError
from app.utils.logger import get_logger
from app.utils.url_normalize import normalize_url
from app.utils.validators import validate_url
from app.utils.verify import verify_download

log = get_logger("manager")


class DownloaderManager:
    def __init__(self, ffmpeg: FFmpegManager, cache_ttl_seconds: float = 300.0) -> None:
        self.ffmpeg = ffmpeg
        self.ytdlp = YtdlpDownloader(ffmpeg)
        self.direct = DirectDownloader()
        self.image = ImageDownloader()
        # Aynı URL'nin tekrar tekrar ağ üzerinden analiz edilmesini önler (performans spec'i
        # madde D). Kısa ömürlü token/direct-URL içerebileceği için TTL ile sınırlıdır.
        self.cache = AnalysisCache(cache_ttl_seconds)

    def set_container_preference(self, container: str) -> None:
        self.ytdlp.container_pref = container

    def set_network(self, proxy_url: str, cookies_browser: str) -> None:
        """Ayarlardan gelen proxy/çerez tercihini tüm adaptörlere uygular."""
        from app.downloaders.http_utils import set_proxy

        self.ytdlp.proxy_url = proxy_url
        self.ytdlp.cookies_browser = cookies_browser
        set_proxy(proxy_url)

    # ------------------------------------------------------------------ analiz
    def analyze(self, raw_url: str, force_refresh: bool = False) -> MediaInfo:
        url = resolve_url(validate_url(raw_url))
        cache_key = normalize_url(url)
        if not force_refresh:
            cached = self.cache.get(cache_key)
            if cached is not None:
                log.info("Analiz (cache'ten): %s", urlsplit(url).hostname)
                return cached

        platform = detect_platform(url)
        log.info("Analiz: %s (%s)", urlsplit(url).hostname, platform.name)  # tam URL kayda yazılmaz (gizlilik)

        if platform.is_direct_media:
            info = self.direct.analyze(url)
        else:
            try:
                info = self.ytdlp.analyze(url)
            except UserError as exc:
                # yt-dlp sadece video arar: fotoğraf/albüm gönderilerinde "medya yok" ya da
                # giriş istiyor hatası verir. Platforma özel yedek yöntem denenir.
                fallback = self._social_fallbacks().get(platform.name)
                if fallback and exc.key in ("no_media", "unsupported", "forbidden"):
                    try:
                        info = fallback(url)
                    except NoMediaError:
                        raise exc from None  # yedek de bulamadıysa asıl (daha bilgilendirici) hata
                elif isinstance(exc, NoMediaError) and platform.html_fallback:
                    info = self.direct.analyze(url)  # yine bulamazsa NoMediaError fırlatır
                else:
                    raise
        if not info.platform:
            info.platform = platform.name
        info.source_url = url
        self.cache.set(cache_key, info)
        return info

    def _social_fallbacks(self):
        return {"X": self._analyze_x_photos, "Instagram": self._analyze_instagram, "TikTok": self._analyze_tiktok}

    def _analyze_tiktok(self, url: str) -> MediaInfo:
        """Fotoğraf gönderisi (/photo/): fotoğrafları ve gönderinin sesini listeler."""
        with make_client() as client:
            post = tiktok.fetch_post(client, url)
            if not post or not post.images:
                raise NoMediaError()
            name = f"tiktok_{post.author or 'gonderi'}_{post.post_id}".strip("_")
            entries = []
            for photo in post.images:
                entry = best_image_entry(client, len(entries) + 1, photo, f"{name}_{len(entries) + 1}")
                if entry:
                    entries.append(entry)
            photo_count = len(entries)
            if post.audio and photo_count:
                try:
                    audio = _entry_from_av(len(entries) + 1, sniff(client, post.audio))
                except Exception:  # noqa: BLE001 - ses adresi alınamadı: sadece fotoğraflar listelenir
                    audio = None
                if audio:
                    audio.title = f"{name}_ses"
                    entries.append(audio)
        if not photo_count:
            raise NoMediaError()
        return MediaInfo(
            source_url=url,
            title=post.description[:80] or name,
            platform="TikTok",
            kind=KIND_IMAGE,
            entries=entries,
            thumbnail=entries[0].thumbnail,
            uploader=post.author,
        )

    def _analyze_instagram(self, url: str) -> MediaInfo:
        """Fotoğraf/albüm/video gönderisi: embed sayfasından tüm medyayı listeler."""
        code = instagram.shortcode(url)
        if not code:
            raise NoMediaError()
        with make_client() as client:
            images, videos = instagram.fetch_media(client, url)
            entries = []
            for video in videos:
                try:
                    entry = _entry_from_av(len(entries) + 1, sniff(client, video))
                except Exception:  # noqa: BLE001 - süresi dolmuş/engelli adres
                    entry = None
                if entry:
                    entry.title = f"instagram_{code}_{len(entries) + 1}"
                    entries.append(entry)
            for photo in images:
                entry = best_image_entry(client, len(entries) + 1, photo, f"instagram_{code}_{len(entries) + 1}")
                if entry:
                    entries.append(entry)
        if not entries:
            raise NoMediaError()
        first_image = next((e for e in entries if e.kind == KIND_IMAGE), None)
        return MediaInfo(
            source_url=url,
            title=f"instagram_{code}",
            platform="Instagram",
            kind=entries[0].kind,
            entries=entries,
            thumbnail=first_image.thumbnail if first_image else "",
        )

    def _analyze_x_photos(self, url: str) -> MediaInfo:
        """Yalnızca fotoğraf içeren tweet: fotoğraf adreslerini alıp en yüksek çözünürlükte listeler."""
        base_url, requested = twitter.strip_media_suffix(url)
        parsed = twitter.parse_status(base_url)
        if not parsed:
            raise NoMediaError()
        user, tweet_id = parsed
        with make_client() as client:
            photo_urls = twitter.fetch_photo_urls(client, base_url)
            entries = []
            for photo in photo_urls:
                entry = best_image_entry(client, len(entries) + 1, photo, f"{user}_{tweet_id}_{len(entries) + 1}")
                if entry:
                    entries.append(entry)
        if not entries:
            raise NoMediaError()
        if requested and not (1 <= requested <= len(entries)):
            requested = None
        return MediaInfo(
            source_url=base_url,
            title=f"{user} - {tweet_id}",
            platform="X",
            kind=KIND_IMAGE,
            entries=entries,
            thumbnail=entries[0].thumbnail,
            uploader=user,
            requested_index=requested,
        )

    def analyze_with_thumbnail(self, raw_url: str) -> MediaInfo:
        """Arka plan iş parçacığı için: analiz + küçük resmi indir."""
        info = self.analyze(raw_url)
        info.thumbnail_bytes = fetch_thumbnail(info.thumbnail)
        return info

    # ------------------------------------------------------------------ indirme
    def download(self, task: DownloadTask, progress: ProgressCallback, control: DownloadControl) -> Path:
        # Duraklatılmış bir görev devam ettiriliyorsa disk alanı vb. tekrar kontrol
        # edilir ama bu, zaten inmiş kısmın üzerine gereksiz bir güvenlik kontrolüdür.
        self._preflight(task)
        backend = task.fmt.backend
        if backend == BACKEND_YTDLP:
            path = self.ytdlp.download(task, progress, control)
        elif backend == BACKEND_IMAGE:
            path = self.image.download(task, progress, control)
        elif backend == BACKEND_DIRECT:
            path = self.direct.download(task, progress, control)
        else:
            raise UserError.from_key("download_failed")

        # Opsiyonel dönüştürme (Gelişmiş): 4K->1080p, WebM->MP4, codec değişimi
        if task.convert and task.fmt.kind == KIND_VIDEO:
            if not self.ffmpeg.is_available:
                raise UserError.from_key("ffmpeg")
            path = convert_file(self.ffmpeg.ffmpeg_path, self.ffmpeg.ffprobe_path, path, task.convert, progress, control)

        # Doğrulama (spec 38): dosya var mı, 0 bayt mı, medya açılabiliyor mu
        verdict = verify_download(path, task.fmt.kind, self.ffmpeg.ffprobe_path)
        if not verdict:
            log.error("Doğrulama başarısız (%s): %s", path.name, verdict.reason)
            raise UserError(f"İndirme doğrulanamadı: {verdict.reason}", "download_failed")
        return path

    def _preflight(self, task: DownloadTask) -> None:
        try:
            task.out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise UserError("İndirme klasörü oluşturulamadı veya yazma izni yok.", "download_failed") from exc
        if task.fmt.needs_ffmpeg and not self.ffmpeg.is_available:
            raise UserError.from_key("ffmpeg")
        size = task.fmt.filesize
        if size:
            factor = 2.3 if task.fmt.is_merge else 1.15
            if shutil.disk_usage(task.out_dir).free < size * factor:
                raise UserError.from_key("disk")
