"""Doğrudan medya URL'leri ve genel web sayfaları (HTML taraması) için adaptör."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.downloaders.base_downloader import (
    BACKEND_DIRECT,
    KIND_AUDIO,
    KIND_IMAGE,
    KIND_VIDEO,
    BaseDownloader,
    DownloadControl,
    DownloadTask,
    MediaEntry,
    MediaFormat,
    MediaInfo,
    ProgressCallback,
)
from app.downloaders.http_utils import SniffResult, ext_for, make_client, sniff, stream_download, url_stem
from app.downloaders.image_downloader import best_image_entry, entry_from_sniff
from app.utils.errors import NoMediaError
from app.utils.logger import get_logger

log = get_logger("direct")

MAX_IMAGES = 30
MAX_AV = 10
MIN_IMAGE_SIDE = 120  # bundan küçük görseller (ikon, izleyici piksel) listelenmez


def _entry_from_av(index: int, sr: SniffResult) -> Optional[MediaEntry]:
    if sr.kind not in (KIND_VIDEO, KIND_AUDIO):
        return None
    fmt = MediaFormat(
        format_id="direct",
        kind=sr.kind,
        container=ext_for(sr.content_type, sr.url, "mp4" if sr.kind == KIND_VIDEO else "mp3"),
        filesize=sr.size,
        backend=BACKEND_DIRECT,
        url=sr.url,
    )
    return MediaEntry(index=index, title=url_stem(sr.url), kind=sr.kind, formats=[fmt], url=sr.url)


def _largest_from_srcset(srcset: str) -> str:
    best_url, best_w = "", -1.0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        weight = 0.0
        if len(bits) > 1:
            try:
                weight = float(bits[1].rstrip("wx"))
            except ValueError:
                weight = 0.0
        if weight > best_w:
            best_url, best_w = bits[0], weight
    return best_url


def _meta_values(soup: BeautifulSoup, names: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for name in names:
        for tag in soup.find_all("meta", attrs={"property": name}) + soup.find_all("meta", attrs={"name": name}):
            content = (tag.get("content") or "").strip()
            if content:
                values.append(content)
    return values


class DirectDownloader(BaseDownloader):
    name = "direct"

    def analyze(self, url: str) -> MediaInfo:
        with make_client() as client:
            sr = sniff(client, url)
            if sr.is_html:
                return self._analyze_html(client, sr)
            entry = entry_from_sniff(1, sr) if sr.kind == KIND_IMAGE else _entry_from_av(1, sr)
        if not entry:
            raise NoMediaError()
        return MediaInfo(
            source_url=url,
            title=entry.title,
            platform="",
            kind=entry.kind,
            entries=[entry],
            thumbnail=entry.thumbnail,
        )

    # ------------------------------------------------------------------ HTML
    def _analyze_html(self, client: httpx.Client, sr: SniffResult) -> MediaInfo:
        soup = BeautifulSoup(sr.head, "html.parser")
        base = sr.url

        def absolute(raw: str) -> str:
            full = urljoin(base, raw.strip())
            return full if urlsplit(full).scheme in ("http", "https") else ""

        videos = _meta_values(soup, ("og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream"))
        for tag in soup.select("video[src], video source[src]"):
            videos.append(tag.get("src", ""))
        audios = [t.get("src", "") for t in soup.select("audio[src], audio source[src]")]

        og_images = _meta_values(soup, ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"))
        images = list(og_images)
        for tag in soup.find_all("img"):
            src = _largest_from_srcset(tag.get("srcset", "")) or tag.get("data-src") or tag.get("data-original") or tag.get("src") or ""
            if src and not src.startswith("data:"):
                images.append(src)

        def dedupe(items: list[str], limit: int) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for raw in items:
                full = absolute(raw) if raw else ""
                if full and full not in seen and not full.lower().split("?")[0].endswith(".svg"):
                    seen.add(full)
                    out.append(full)
                if len(out) >= limit:
                    break
            return out

        video_urls = dedupe(videos, MAX_AV)
        audio_urls = dedupe(audios, MAX_AV)
        image_urls = dedupe(images, MAX_IMAGES)
        og_set = {absolute(u) for u in og_images}

        def probe_av(u: str) -> Optional[MediaEntry]:
            try:
                return _entry_from_av(0, sniff(client, u))
            except Exception:  # noqa: BLE001
                return None

        def probe_img(u: str) -> Optional[MediaEntry]:
            entry = best_image_entry(client, 0, u)
            if not entry:
                return None
            fmt = entry.formats[0]
            small = fmt.width and fmt.height and min(fmt.width, fmt.height) < MIN_IMAGE_SIDE
            return None if small and u not in og_set else entry

        with ThreadPoolExecutor(max_workers=6) as pool:
            av = list(pool.map(probe_av, video_urls + audio_urls))
            imgs = list(pool.map(probe_img, image_urls))

        entries = [e for e in av + imgs if e]
        seen_urls: set[str] = set()
        unique: list[MediaEntry] = []
        for e in entries:
            if e.url not in seen_urls:
                seen_urls.add(e.url)
                unique.append(e)
        for i, e in enumerate(unique, 1):
            e.index = i
        if not unique:
            raise NoMediaError()

        title_candidates = _meta_values(soup, ("og:title", "twitter:title"))
        title = title_candidates[0] if title_candidates else (soup.title.get_text(strip=True) if soup.title else "")
        title = title or urlsplit(sr.url).hostname or "Web sayfası"
        first = unique[0]
        thumb = next((e.thumbnail for e in unique if e.kind == KIND_IMAGE), "")
        return MediaInfo(
            source_url=sr.url,
            title=title,
            platform="",
            kind=first.kind,
            entries=unique,
            thumbnail=thumb,
        )

    def download(self, task: DownloadTask, progress: ProgressCallback, control: DownloadControl) -> Path:
        return stream_download(
            task.fmt.url, task.out_dir, task.base_name, task.fmt.container, task.conflict, progress, control,
            task.rate_limit_bps, task.max_retries, task.backoff_start,
        )
