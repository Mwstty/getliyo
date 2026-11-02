"""Ortak veri modelleri ve downloader taban sınıfı."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

KIND_VIDEO = "video"
KIND_IMAGE = "image"
KIND_AUDIO = "audio"

BACKEND_YTDLP = "ytdlp"
BACKEND_DIRECT = "direct"
BACKEND_IMAGE = "image"


@dataclass
class MediaFormat:
    """Kullanıcının seçebileceği tek bir indirme seçeneği (tablodaki bir satır)."""

    format_id: str
    kind: str
    resolution: str = ""  # "1080p" veya "3840×2160"
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: str = ""
    filesize: Optional[int] = None
    size_estimated: bool = False
    container: str = ""  # çıktı uzantısı: mp4, jpg, mp3 ...
    backend: str = BACKEND_YTDLP
    selector: str = ""  # yt-dlp format seçici ("137+140")
    url: str = ""  # doğrudan indirme adresi (direct/image backend)
    is_merge: bool = False  # video+ses birleştirilecek mi
    needs_ffmpeg: bool = False
    bitrate: Optional[float] = None  # kbps
    language: str = ""


@dataclass
class MediaEntry:
    """Bir URL içindeki tek medya öğesi (galeride her fotoğraf/video ayrı entry)."""

    index: int
    title: str
    kind: str
    formats: list[MediaFormat]
    thumbnail: str = ""
    duration: Optional[float] = None
    media_id: str = ""
    url: str = ""  # indirme sırasında kullanılacak URL
    playlist_index: Optional[int] = None
    uploader: str = ""
    original_index: int = 0  # kaynaktaki asıl sıra (index ile aynı, MediaItem sözleşmesi için)
    platform: str = ""
    upload_date: str = ""  # YYYY-MM-DD
    description: str = ""
    subtitles: list[str] = field(default_factory=list)  # mevcut altyazı dilleri
    chapters: int = 0
    audio_tracks: list[tuple[str, str]] = field(default_factory=list)  # (format_id, etiket) — 2+ ise seçilebilir
    thumbnail_url: str = ""

    def __post_init__(self) -> None:
        if not self.original_index:
            self.original_index = self.index


@dataclass
class MediaInfo:
    source_url: str
    title: str
    platform: str
    kind: str
    entries: list[MediaEntry]
    duration: Optional[float] = None
    thumbnail: str = ""
    thumbnail_bytes: Optional[bytes] = None
    uploader: str = ""
    requested_index: Optional[int] = None  # ör. X'in /photo/2 deep-link'i -> 2

    @property
    def is_gallery(self) -> bool:
        return len(self.entries) > 1


@dataclass
class ConvertSpec:
    """İndirme sonrası FFmpeg dönüştürme (Gelişmiş). codec: h264|h265|vp9|av1, container: mp4|mkv|webm."""

    codec: str = "h264"
    container: str = "mp4"
    max_height: Optional[int] = None


@dataclass
class DownloadTask:
    title: str
    url: str
    fmt: MediaFormat
    out_dir: Path
    base_name: str
    conflict: str = "new"
    playlist_index: Optional[int] = None
    platform: str = ""
    rate_limit_bps: int = 0  # 0 = sınırsız (bayt/sn)
    max_retries: int = 5
    backoff_start: int = 5  # sn; 3/5/10/30 kademeli artar
    subtitle_langs: list[str] = field(default_factory=list)
    subtitle_format: str = "srt"  # srt | vtt
    embed_subs: bool = False
    embed_metadata: bool = True  # metadata + chapters dosyaya yazılır
    embed_thumbnail: bool = False
    proxy_url: str = ""  # şifre içerebilir: ASLA loglanmaz
    cookies_browser: str = ""  # "", chrome, edge, firefox — kullanıcı açıkça izin verdiyse
    convert: Optional[ConvertSpec] = None
    history_id: Optional[int] = None


@dataclass
class DownloadControl:
    """Bir indirmeyi durdurma sinyali. 'keep_partial' iptal ile duraklatmayı ayırır:

    - Gerçek İPTAL: stop_event set edilir, keep_partial=False -> yarım dosya silinir.
    - DURAKLAT: stop_event set edilir, keep_partial=True -> yarım dosya (.part) SİLİNMEZ;
      sonradan aynı görev tekrar başlatılırsa (RESUME) yt-dlp (continuedl) veya bizim
      Range-header mantığımız kaldığı yerden devam eder.
    """

    stop_event: threading.Event = field(default_factory=threading.Event)
    keep_partial: bool = False

    def stop(self, *, keep_partial: bool = False) -> None:
        self.keep_partial = keep_partial
        self.stop_event.set()

    def is_set(self) -> bool:  # threading.Event ile uyumlu kısayol
        return self.stop_event.is_set()


@dataclass
class ProgressInfo:
    status: str = ""
    percent: Optional[float] = None  # 0..100, bilinmiyorsa None
    done_bytes: int = 0
    total_bytes: Optional[int] = None
    speed: Optional[float] = None  # bayt/sn
    eta: Optional[float] = None  # sn
    filename: str = ""
    indeterminate: bool = False


ProgressCallback = Callable[[ProgressInfo], None]


class BaseDownloader(ABC):
    """Tüm downloader adaptörlerinin uyması gereken arayüz."""

    name: str = "base"

    @abstractmethod
    def analyze(self, url: str) -> MediaInfo:
        """URL'yi inceler; indirilebilir medya bulunamazsa NoMediaError fırlatır."""

    @abstractmethod
    def download(
        self, task: DownloadTask, progress: ProgressCallback, control: "DownloadControl"
    ) -> Path:
        """Görevi indirir, oluşan dosya yolunu döndürür. control.stop_event set edilirse
        ve control.keep_partial True ise indirme DURAKLATILMIŞ sayılır (dosya korunur)."""
