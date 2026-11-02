"""Doğrudan URL'ler için HTTP yardımcıları: keşif (sniff), akış indirme, küçük resim."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlsplit

import httpx

from app.downloaders.base_downloader import (
    KIND_AUDIO,
    KIND_IMAGE,
    KIND_VIDEO,
    DownloadControl,
    ProgressCallback,
    ProgressInfo,
)
from app.media.media_utils import AUDIO_EXTS, IMAGE_EXTS, MIME_TO_EXT, VIDEO_EXTS
from app.utils.errors import CancelledError, SkippedError, UserError
from app.utils.filename import resolve_base_name
from app.utils.retry import backoff_seconds
from app.utils.logger import get_logger
from app.utils.net_guard import guard_request

log = get_logger("http")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) getliyo/1.0"
HTML_TYPES = {"text/html", "application/xhtml+xml"}
CHUNK = 64 * 1024


_MAX_BYTES = 0  # 0 = sınırsız; sunucu modunda disk korumak için ayarlanır


def set_max_download_bytes(n: int) -> None:
    global _MAX_BYTES
    _MAX_BYTES = max(0, int(n))


_PROXY: str = ""  # şifre içerebilir — ASLA loglanmaz


def set_proxy(url: str) -> None:
    """Tüm doğrudan HTTP istekleri (analiz/indirme/thumbnail) için proxy. Boş = kapalı."""
    global _PROXY
    _PROXY = url or ""


def make_client() -> httpx.Client:
    kwargs: dict = {}
    if _PROXY:
        kwargs["proxy"] = _PROXY
    return httpx.Client(
        follow_redirects=True,
        event_hooks={"request": [guard_request]},
        timeout=httpx.Timeout(15.0, read=30.0),
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        **kwargs,
    )


_REFERERS = (
    ("tiktokcdn", "https://www.tiktok.com/"),
    ("tiktokv", "https://www.tiktok.com/"),
    ("ibyteimg", "https://www.tiktok.com/"),
    ("byteoversea", "https://www.tiktok.com/"),
)


def referer_headers(url: str) -> dict[str, str]:
    """Bazı CDN'ler (TikTok) Referer olmadan 403 verir; ilgili adresler için ekler."""
    host = (urlsplit(url).hostname or "").lower()
    for marker, referer in _REFERERS:
        if marker in host:
            return {"Referer": referer}
    return {}


def url_extension(url: str) -> str:
    path = unquote(urlsplit(url).path)
    ext = os.path.splitext(path)[1].lstrip(".").lower()
    return ext


def url_stem(url: str) -> str:
    parts = urlsplit(url)
    stem = os.path.splitext(os.path.basename(unquote(parts.path)))[0]
    return stem or (parts.hostname or "dosya")


def kind_from(content_type: str, url: str) -> Optional[str]:
    """Content-Type (yoksa URL uzantısı) üzerinden medya türü."""
    if content_type.startswith("image/"):
        return KIND_IMAGE
    if content_type.startswith("video/"):
        return KIND_VIDEO
    if content_type.startswith("audio/"):
        return KIND_AUDIO
    ext = url_extension(url)
    if ext in IMAGE_EXTS:
        return KIND_IMAGE
    if ext in VIDEO_EXTS:
        return KIND_VIDEO
    if ext in AUDIO_EXTS:
        return KIND_AUDIO
    return None


def ext_for(content_type: str, url: str, default: str = "bin") -> str:
    ext = MIME_TO_EXT.get(content_type)
    if ext:
        return ext
    url_ext = url_extension(url)
    if url_ext in IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS:
        return "jpg" if url_ext == "jpeg" else url_ext
    return default


@dataclass
class SniffResult:
    url: str
    content_type: str
    size: Optional[int]
    head: bytes = b""  # HTML ise sayfa (en fazla 3 MB), görsel ise ilk 256 KB
    kind: Optional[str] = None

    @property
    def is_html(self) -> bool:
        return self.content_type in HTML_TYPES


def sniff(client: httpx.Client, url: str) -> SniffResult:
    """URL'nin ne olduğunu öğrenir; gövdeyi gereğinden fazla indirmez."""
    with client.stream("GET", url, headers=referer_headers(url)) as resp:
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        size = int(resp.headers["content-length"]) if resp.headers.get("content-length", "").isdigit() else None
        final_url = str(resp.url)
        kind = kind_from(ctype, final_url)
        limit = 3_000_000 if ctype in HTML_TYPES else (262_144 if kind == KIND_IMAGE else 0)
        buf = bytearray()
        if limit:
            for chunk in resp.iter_bytes(CHUNK):
                buf += chunk
                if len(buf) >= limit:
                    break
    return SniffResult(final_url, ctype, size, bytes(buf), kind)


_THUMB_CACHE = None  # set_thumbnail_cache_dir() ile kurulur (spec madde 53: aynı thumbnail tekrar inmesin)


def set_thumbnail_cache_dir(path) -> None:
    global _THUMB_CACHE
    from app.utils.thumb_cache import ThumbCache

    _THUMB_CACHE = ThumbCache(path, _fetch_thumbnail_uncached)


def _fetch_thumbnail_uncached(url: str, limit: int = 3_000_000) -> Optional[bytes]:
    if not url.startswith(("http://", "https://")):
        return None
    try:
        with make_client() as client, client.stream("GET", url) as resp:
            resp.raise_for_status()
            buf = bytearray()
            for chunk in resp.iter_bytes(CHUNK):
                buf += chunk
                if len(buf) > limit:
                    return None
            return bytes(buf)
    except (httpx.HTTPError, OSError):
        log.info("Küçük resim alınamadı: %s", url)
        return None


def fetch_thumbnail(url: str, limit: int = 3_000_000) -> Optional[bytes]:
    """Küçük resmi indirir (arayüz iş parçacığında ÇAĞIRMA). Hata olursa None. Ayarlıysa disk
    önbelleğini kullanır — aynı thumbnail iki kez indirilmez."""
    if _THUMB_CACHE is not None:
        return _THUMB_CACHE.get(url)
    return _fetch_thumbnail_uncached(url, limit)


def stream_download(
    url: str,
    out_dir: Path,
    base: str,
    ext_hint: str,
    conflict: str,
    progress: ProgressCallback,
    control: "DownloadControl",
    rate_limit_bps: int = 0,
    max_retries: int = 5,
    backoff_start: int = 3,
    sleep=time.sleep,
) -> Path:
    """URL'yi parça parça indirir.

    - Duraklat/devam: diskte '.part' varsa 'Range: bytes=N-' ile kaldığı yerden devam eder
      (sunucu 206 dönerse; dönmezse baştan).
    - Bağlantı koparsa (ağ hatası) max_retries kez, 3/5/10/30 sn kademeli bekleyerek
      OTOMATİK yeniden dener; her deneme .part'tan devam eder.
    - control.keep_partial True ise (DURAKLAT) .part silinmez; False ise (İPTAL) silinir.
    - rate_limit_bps > 0 ise hız sınırlanır.
    """
    base, skip = resolve_base_name(out_dir, base, conflict)
    if skip:
        raise SkippedError(str(skip))

    attempt = 0
    while True:
        try:
            return _stream_once(url, out_dir, base, ext_hint, progress, control, rate_limit_bps)
        except (httpx.TransportError, httpx.RemoteProtocolError) as exc:
            if control.is_set() or attempt >= max_retries:
                raise
            wait = backoff_seconds(attempt, backoff_start)
            attempt += 1
            log.warning("Bağlantı koptu, %s sn sonra yeniden denenecek (%s/%s): %s", wait, attempt, max_retries, type(exc).__name__)
            progress(ProgressInfo(status=f"Bağlantı koptu, {wait} sn sonra tekrar denenecek ({attempt}/{max_retries})", indeterminate=True))
            for _ in range(wait * 10):  # bekleme sırasında iptal/duraklat'a hızlı tepki ver
                if control.is_set():
                    raise CancelledError() from exc
                sleep(0.1)


def _stream_once(
    url: str,
    out_dir: Path,
    base: str,
    ext_hint: str,
    progress: ProgressCallback,
    control: "DownloadControl",
    rate_limit_bps: int,
) -> Path:
    tmp = out_dir / f"{base}.{ext_hint}.part" if ext_hint else None
    resume_from = tmp.stat().st_size if tmp and tmp.exists() else 0
    headers = ({"Range": f"bytes={resume_from}-"} if resume_from else {}) | referer_headers(url)

    with make_client() as client, client.stream("GET", url, headers=headers) as resp:
        if resume_from and resp.status_code == 416:  # istenen aralık dosya boyutunu aşıyor: zaten tam inmiş olabilir
            resume_from = 0
            resp.close()
            return _stream_once_fresh(url, out_dir, base, ext_hint, progress, control, rate_limit_bps)
        resp.raise_for_status()
        resumed = resume_from > 0 and resp.status_code == 206
        if resume_from and not resumed:
            resume_from = 0  # sunucu range desteklemedi, baştan
        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        content_len = int(resp.headers["content-length"]) if resp.headers.get("content-length", "").isdigit() else None
        total = (resume_from + content_len) if content_len is not None else None
        ext = ext_hint or ext_for(ctype, url)
        final = out_dir / f"{base}.{ext}"
        tmp = out_dir / f"{base}.{ext}.part"
        done = resume_from
        start = time.monotonic()
        last = 0.0
        try:
            with open(tmp, "ab" if resumed else "wb") as fh:
                for chunk in resp.iter_bytes(CHUNK):
                    if control.is_set():
                        raise CancelledError()
                    fh.write(chunk)
                    done += len(chunk)
                    if _MAX_BYTES and done > _MAX_BYTES:
                        raise UserError("Dosya sunucu sınırını aşıyor.", "disk")
                    now = time.monotonic()
                    elapsed = max(now - start, 1e-6)
                    if rate_limit_bps > 0:
                        expected = (done - resume_from) / rate_limit_bps
                        if expected > elapsed:
                            time.sleep(min(expected - elapsed, 1.0))
                            now = time.monotonic()
                            elapsed = max(now - start, 1e-6)
                    if now - last >= 0.1:
                        last = now
                        speed = (done - resume_from) / elapsed
                        eta = (total - done) / speed if total and speed else None
                        progress(
                            ProgressInfo(
                                status="İndiriliyor",
                                percent=(done / total * 100) if total else None,
                                done_bytes=done,
                                total_bytes=total,
                                speed=speed,
                                eta=eta,
                                filename=final.name,
                                indeterminate=total is None,
                            )
                        )
            if total is not None and done < total:
                raise httpx.RemoteProtocolError("Bağlantı eksik veriyle kapandı")
            os.replace(tmp, final)
        except CancelledError:
            if not control.keep_partial:
                tmp.unlink(missing_ok=True)
            raise
        except httpx.TransportError:
            raise  # .part kalır, retry döngüsü kaldığı yerden devam eder
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    progress(ProgressInfo(status="Tamamlandı", percent=100.0, done_bytes=done, total_bytes=done, filename=final.name))
    return final


def _stream_once_fresh(url, out_dir, base, ext_hint, progress, control, rate_limit_bps) -> Path:
    if ext_hint:
        (out_dir / f"{base}.{ext_hint}.part").unlink(missing_ok=True)
    return _stream_once(url, out_dir, base, ext_hint, progress, control, rate_limit_bps)
