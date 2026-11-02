"""Görsel adaptörü: gerçek çözünürlüğü ölçer, uzantıyı doğru algılar, orijinal boyutu tercih eder."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from PIL import Image

from app.downloaders.base_downloader import (
    BACKEND_IMAGE,
    KIND_IMAGE,
    BaseDownloader,
    DownloadControl,
    DownloadTask,
    MediaEntry,
    MediaFormat,
    MediaInfo,
    ProgressCallback,
)
from app.downloaders.http_utils import SniffResult, ext_for, make_client, sniff, stream_download, url_stem
from app.platforms import image_candidates
from app.utils.errors import NoMediaError
from app.utils.logger import get_logger

log = get_logger("image")

_PIL_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "AVIF": "avif", "BMP": "bmp"}


def probe_image(head: bytes) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Baştaki baytlardan (genişlik, yükseklik, uzantı). Okunamazsa (None, None, None)."""
    if not head:
        return None, None, None
    try:
        with Image.open(io.BytesIO(head)) as im:
            width, height = im.size
            return width, height, _PIL_EXT.get((im.format or "").upper())
    except Exception:  # noqa: BLE001 - desteklenmeyen/kesik görsel: sadece ölçemeyiz
        return None, None, None


def entry_from_sniff(index: int, sr: SniffResult, title: str = "") -> Optional[MediaEntry]:
    if sr.kind != KIND_IMAGE:
        return None
    width, height, pil_ext = probe_image(sr.head)
    ext = pil_ext or ext_for(sr.content_type, sr.url, "jpg")
    fmt = MediaFormat(
        format_id="image",
        kind=KIND_IMAGE,
        resolution=f"{width}×{height}" if width and height else "",
        width=width,
        height=height,
        codec="",
        filesize=sr.size,
        container=ext,
        backend=BACKEND_IMAGE,
        url=sr.url,
    )
    return MediaEntry(
        index=index,
        title=title or url_stem(sr.url),
        kind=KIND_IMAGE,
        formats=[fmt],
        thumbnail=sr.url,
        url=sr.url,
    )


def best_image_entry(client, index: int, url: str, title: str = "") -> Optional[MediaEntry]:
    """Yüksek çözünürlüklü varyantı önce dener, olmazsa verilen adrese döner."""
    for candidate in image_candidates(url):
        try:
            entry = entry_from_sniff(index, sniff(client, candidate), title)
        except Exception:  # noqa: BLE001 - varyant yoksa sıradakine geç
            log.info("Görsel adresi kullanılamadı: %s", candidate)
            continue
        if entry:
            return entry
    return None


class ImageDownloader(BaseDownloader):
    name = "image"

    def analyze(self, url: str) -> MediaInfo:
        with make_client() as client:
            entry = best_image_entry(client, 1, url)
        if not entry:
            raise NoMediaError()
        return MediaInfo(
            source_url=url,
            title=entry.title,
            platform="",
            kind=KIND_IMAGE,
            entries=[entry],
            thumbnail=entry.thumbnail,
        )

    def download(self, task: DownloadTask, progress: ProgressCallback, control: DownloadControl) -> Path:
        return stream_download(
            task.fmt.url, task.out_dir, task.base_name, task.fmt.container, task.conflict, progress, control,
            task.rate_limit_bps, task.max_retries, task.backoff_start,
        )
