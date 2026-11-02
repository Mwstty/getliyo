"""yt-dlp adaptörü: YouTube, Instagram, X, TikTok, Facebook, Reddit, Twitch ve yt-dlp'nin desteklediği diğer siteler."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import yt_dlp
from yt_dlp.utils import DownloadError

from app.downloaders.base_downloader import (
    BACKEND_YTDLP,
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
    ProgressInfo,
)
from app.media.ffmpeg_manager import FFmpegManager
from app.media.media_utils import AUDIO_EXTS, IMAGE_EXTS
from app.platforms.twitter import strip_media_suffix as strip_x_media_suffix
from app.utils.errors import CancelledError, NoMediaError, SkippedError, UserError, error_key, friendly_message
from app.utils.filename import resolve_base_name
from app.utils.retry import backoff_seconds
from app.utils.logger import get_logger

log = get_logger("ytdlp")

PLAYLIST_LIMIT = 50
AUDIO_TARGETS = [("mp3", "MP3"), ("m4a", "M4A"), ("wav", "WAV"), ("opus", "Opus"), ("flac", "FLAC")]
_CODEC_LABELS = [
    (("avc", "h264"), "AVC"),
    (("hev", "hvc", "h265"), "HEVC"),
    (("vp09", "vp9"), "VP9"),
    (("vp08", "vp8"), "VP8"),
    (("av01", "av1"), "AV1"),
    (("mp4a", "aac"), "AAC"),
    (("opus",), "Opus"),
    (("mp3",), "MP3"),
    (("flac",), "FLAC"),
    (("vorbis",), "Vorbis"),
    (("ec-3", "eac3"), "E-AC3"),
    (("ac-3", "ac3"), "AC3"),
]


# --------------------------------------------------------------------------- saf (test edilebilir) mantık
def codec_family(codec: Optional[str]) -> str:
    if not codec or codec == "none":
        return ""
    low = codec.lower()
    for prefixes, label in _CODEC_LABELS:
        if low.startswith(prefixes):
            return label
    return low.split(".")[0].upper()


def choose_container(vcodec: str, preferred: str) -> str:
    """WebM yalnızca VP8/VP9/AV1 taşır; uymuyorsa MKV'ye düşer."""
    if preferred == "webm" and vcodec not in ("VP9", "VP8", "AV1"):
        return "mkv"
    return preferred


def _size_of(f: dict[str, Any], duration: Optional[float]) -> tuple[Optional[int], bool]:
    exact = f.get("filesize")
    if exact:
        return int(exact), False
    approx = f.get("filesize_approx")
    if approx:
        return int(approx), True
    tbr = f.get("tbr") or 0
    if tbr and duration:
        return int(tbr * 125 * duration), True
    return None, False


def _classify(f: dict[str, Any]) -> Optional[str]:
    ext = (f.get("ext") or "").lower()
    vc, ac = f.get("vcodec"), f.get("acodec")
    if ext == "mhtml" or f.get("protocol") == "mhtml" or "storyboard" in (f.get("format_note") or "").lower():
        return None
    if ext in IMAGE_EXTS:
        return KIND_IMAGE
    if vc == "none":
        return KIND_AUDIO if (ac not in (None, "none") or ext in AUDIO_EXTS or f.get("abr")) else None
    if f.get("height") or vc not in (None, "none"):
        return KIND_VIDEO
    if ext in AUDIO_EXTS:
        return KIND_AUDIO
    return None


def _audio_estimate(target: str, source: Optional[int], duration: Optional[float]) -> tuple[Optional[int], bool]:
    if not duration:
        return (source, True) if source else (None, False)
    if target == "mp3":
        return int(duration * 24000), True
    if target == "wav":
        return int(duration * 176400), True
    if target == "flac":
        return int(duration * 176400 * 0.6), True
    return (source, True) if source else (int(duration * 16000), True)


def build_formats(info: dict[str, Any], container_pref: str = "mp4") -> tuple[Optional[str], list[MediaFormat]]:
    """yt-dlp `info` sözlüğünden kullanıcıya gösterilecek format listesini üretir."""
    duration = info.get("duration")
    raw = info.get("formats") or ([{**info, "format_id": info.get("format_id") or "0"}] if info.get("url") else [])

    videos: list[dict[str, Any]] = []
    audios: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    for f in raw:
        kind = _classify(f)
        if kind == KIND_VIDEO:
            videos.append(f)
        elif kind == KIND_AUDIO:
            audios.append(f)
        elif kind == KIND_IMAGE:
            images.append(f)

    def abr(f: dict[str, Any]) -> float:
        return float(f.get("abr") or f.get("tbr") or 0)

    audios.sort(key=abr, reverse=True)

    def best_audio_for(container: str) -> Optional[dict[str, Any]]:
        if not audios:
            return None
        want = {"mp4": ("m4a", "mp4", "aac"), "webm": ("webm", "opus", "ogg")}.get(container)
        if want:
            for a in audios:
                if (a.get("ext") or "").lower() in want:
                    return a
        return audios[0]

    rows: dict[tuple[int, int, str], tuple[float, MediaFormat]] = {}
    for f in videos:
        height = int(f.get("height") or 0)
        if height <= 0:
            continue
        family = codec_family(f.get("vcodec")) or (f.get("ext") or "").upper()
        fps = f.get("fps")
        video_only = f.get("acodec") == "none"
        container = choose_container(family, container_pref)
        size, est = _size_of(f, duration)
        selector = str(f["format_id"])
        is_merge = False
        audio = best_audio_for(container) if video_only else None
        if audio is not None:
            a_size, a_est = _size_of(audio, duration)
            total = (size or 0) + (a_size or 0)
            est = est or a_est or size is None or a_size is None
            size = total or None
            selector = f"{f['format_id']}+{audio['format_id']}"
            is_merge = True
        codec = family + (" HDR" if f.get("dynamic_range") not in (None, "SDR") else "")
        fmt = MediaFormat(
            format_id=selector,
            kind=KIND_VIDEO,
            resolution=f"{height}p",
            width=f.get("width"),
            height=height,
            fps=float(fps) if fps else None,
            codec=codec,
            filesize=size,
            size_estimated=est,
            container=container,
            backend=BACKEND_YTDLP,
            selector=selector,
            is_merge=is_merge,
            needs_ffmpeg=is_merge,
            bitrate=float(f.get("tbr")) if f.get("tbr") else None,
        )
        key = (height, int(round(fps or 0)), family)
        score = float(f.get("tbr") or f.get("vbr") or 0)
        if key not in rows or score > rows[key][0]:
            rows[key] = (score, fmt)
    ranked = sorted(rows.values(), key=lambda t: (-(t[1].height or 0), -(t[1].fps or 0), -t[0]))
    video_fmts = [fmt for _score, fmt in ranked]

    image_fmts: list[MediaFormat] = []
    for f in images:
        w, h = f.get("width"), f.get("height")
        image_fmts.append(
            MediaFormat(
                format_id=str(f["format_id"]),
                kind=KIND_IMAGE,
                resolution=f"{w}×{h}" if w and h else "",
                width=w,
                height=h,
                filesize=f.get("filesize") or f.get("filesize_approx"),
                container=(f.get("ext") or "jpg").lower().replace("jpeg", "jpg"),
                backend=BACKEND_YTDLP,
                selector=str(f["format_id"]),
                url=f.get("url") or "",
            )
        )
    image_fmts.sort(key=lambda m: -((m.width or 0) * (m.height or 0)))

    audio_fmts: list[MediaFormat] = []
    if video_fmts or audios:
        src = audios[0] if audios else None
        src_size, _ = _size_of(src, duration) if src else (None, False)
        src_codec = codec_family(src.get("acodec")) if src else ""
        for ext, label in AUDIO_TARGETS:
            size, est = _audio_estimate(ext, src_size, duration)
            audio_fmts.append(
                MediaFormat(
                    format_id=f"audio-{ext}",
                    kind=KIND_AUDIO,
                    codec=src_codec,
                    filesize=size,
                    size_estimated=est,
                    container=ext,
                    backend=BACKEND_YTDLP,
                    selector="bestaudio/best",
                    needs_ffmpeg=True,
                )
            )

    if video_fmts:
        return KIND_VIDEO, video_fmts + audio_fmts
    if image_fmts and not audios:
        return KIND_IMAGE, image_fmts
    if audios:
        return KIND_AUDIO, audio_fmts
    return None, []


def audio_tracks_from(info: dict[str, Any]) -> list[tuple[str, str]]:
    """Birden fazla DİL için ses akışı varsa [(format_id, 'tr — 128k'), ...]; yoksa boş (seçim gerekmez)."""
    best: dict[str, tuple[float, str]] = {}
    for f in info.get("formats") or []:
        if _classify(f) != KIND_AUDIO:
            continue
        lang = str(f.get("language") or "").strip()
        if not lang:
            continue
        score = float(f.get("abr") or f.get("tbr") or 0)
        if lang not in best or score > best[lang][0]:
            best[lang] = (score, str(f["format_id"]))
    if len(best) < 2:
        return []
    return [(fid, f"{lang} — {int(score)}k") for lang, (score, fid) in sorted(best.items())]


def _fmt_date(raw: Any) -> str:
    text = str(raw or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) == 8 and text.isdigit() else ""


def entry_from_info(info: dict[str, Any], index: int, container_pref: str = "mp4") -> Optional[MediaEntry]:
    kind, formats = build_formats(info, container_pref)
    if not kind or not formats:
        return None
    thumb = info.get("thumbnail") or ""
    if not thumb and info.get("thumbnails"):
        thumb = (info["thumbnails"][-1] or {}).get("url", "")
    if not thumb and kind == KIND_IMAGE:
        thumb = formats[0].url
    return MediaEntry(
        index=index,
        title=info.get("title") or info.get("id") or f"Medya {index}",
        kind=kind,
        formats=formats,
        thumbnail=thumb,
        duration=info.get("duration"),
        media_id=str(info.get("id") or ""),
        url=info.get("webpage_url") or info.get("original_url") or "",
        uploader=str(info.get("uploader") or info.get("channel") or info.get("uploader_id") or ""),
        platform=str(info.get("extractor_key") or ""),
        upload_date=_fmt_date(info.get("upload_date")),
        description=str(info.get("description") or "")[:2000],
        subtitles=sorted(k for k in (info.get("subtitles") or {}) if k != "live_chat"),
        chapters=len(info.get("chapters") or []),
        audio_tracks=audio_tracks_from(info) if kind == KIND_VIDEO else [],
        thumbnail_url=thumb,
    )


def build_download_opts(
    base: dict[str, Any], task: DownloadTask, base_name: str, hook: Any = None, pp_hook: Any = None
) -> dict[str, Any]:
    """yt-dlp indirme seçenekleri. Ayrı fonksiyon: ağ olmadan test edilebilir."""
    fmt = task.fmt
    opts: dict[str, Any] = base | {
        "format": fmt.selector or "best",
        "outtmpl": {"default": str(task.out_dir / (base_name.replace("%", "%%") + ".%(ext)s"))},
        "overwrites": task.conflict == "overwrite",
        "windowsfilenames": True,
        "concurrent_fragment_downloads": 4,
        "continuedl": True,
        "noprogress": True,
        "retries": task.max_retries,
        "fragment_retries": task.max_retries,
        "retry_sleep_functions": {
            "http": lambda n: backoff_seconds(n, task.backoff_start),
            "fragment": lambda n: backoff_seconds(n, task.backoff_start),
        },
    }
    if hook:
        opts["progress_hooks"] = [hook]
    if pp_hook:
        opts["postprocessor_hooks"] = [pp_hook]
    if task.rate_limit_bps > 0:
        opts["ratelimit"] = task.rate_limit_bps
    if task.proxy_url and "proxy" not in opts:
        opts["proxy"] = task.proxy_url
    if task.cookies_browser and "cookiesfrombrowser" not in opts:
        opts["cookiesfrombrowser"] = (task.cookies_browser,)
    if task.playlist_index:
        opts["playlist_items"] = str(task.playlist_index)

    pps: list[dict[str, Any]] = []
    if fmt.kind == KIND_VIDEO:
        opts["merge_output_format"] = fmt.container
        if task.subtitle_langs:
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = list(task.subtitle_langs)
            opts["subtitlesformat"] = f"{task.subtitle_format}/best"
            pps.append({"key": "FFmpegSubtitlesConvertor", "format": task.subtitle_format})
            if task.embed_subs:
                pps.append({"key": "FFmpegEmbedSubtitle"})
    elif fmt.kind == KIND_AUDIO:
        pps.append(
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt.container,
                "preferredquality": "0" if fmt.container == "mp3" else "192",
            }
        )
    if fmt.kind in (KIND_VIDEO, KIND_AUDIO):
        if task.embed_metadata:
            pps.append({"key": "FFmpegMetadata", "add_metadata": True, "add_chapters": True})
        if task.embed_thumbnail:
            opts["writethumbnail"] = True
            pps.append({"key": "EmbedThumbnail"})
    if pps:
        opts["postprocessors"] = pps
    return opts


# --------------------------------------------------------------------------- adaptör
class _YdlLogger:
    """yt-dlp'nin konsol çıktısını log dosyasına yönlendirir."""

    def debug(self, msg: str) -> None:
        log.debug(msg)

    def info(self, msg: str) -> None:
        log.debug(msg)

    def warning(self, msg: str) -> None:
        log.warning(msg)

    def error(self, msg: str) -> None:
        log.error(msg)


class YtdlpDownloader(BaseDownloader):
    name = "ytdlp"

    def __init__(self, ffmpeg: FFmpegManager, container_pref: str = "mp4") -> None:
        self.ffmpeg = ffmpeg
        self.container_pref = container_pref
        self.proxy_url = ""  # şifre içerebilir: loglanmaz
        self.cookies_browser = ""  # yalnızca kullanıcı Gelişmiş ayarda açıkça izin verdiyse

    # ------------------------------------------------------------ ortak seçenekler
    def _base_opts(self) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "noplaylist": True,
            "playlistend": PLAYLIST_LIMIT,
            "socket_timeout": 20,
            "retries": 5,
            "logger": _YdlLogger(),
        }
        if self.ffmpeg.directory:
            opts["ffmpeg_location"] = str(self.ffmpeg.directory)
        deno = self.ffmpeg.deno_path
        if deno:  # YouTube için JavaScript çalışma zamanı
            opts["js_runtimes"] = {"deno": {"path": str(deno)}}
        if self.proxy_url:
            opts["proxy"] = self.proxy_url
        if self.cookies_browser:  # yt-dlp tarayıcı çerezlerini KENDİ okur; biz düz metin dışa aktarmayız
            opts["cookiesfrombrowser"] = (self.cookies_browser,)
        return opts

    # ------------------------------------------------------------ analiz
    def analyze(self, url: str) -> MediaInfo:
        # KRİTİK BUG DÜZELTMESİ: X'in ".../photo/2" gibi deep-link'leri yt-dlp'yi o
        # öğeyi zorla video sanmaya iter ve "Media #N is not a video" ile patlar.
        # Asıl tweet adresini analiz edip istenen index'i ayrıca not ediyoruz.
        base_url, requested_index = strip_x_media_suffix(url)
        opts = self._base_opts() | {"skip_download": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(base_url, download=False)
        except DownloadError as exc:
            log.warning("yt-dlp analiz hatası (%s): %s", base_url, exc)
            if "is not a video" in str(exc).lower():
                # Savunma amaçlı: yukarıdaki URL temizliğine rağmen yt-dlp yine de bu
                # hatayı verirse (ör. farklı bir platformda benzer bir durum), kullanıcıya
                # anlaşılır bir mesaj göster; ham hatayı asla gösterme.
                raise UserError.from_key("not_a_video") from exc
            key = error_key(exc)
            if key in ("unsupported", "no_media"):
                raise NoMediaError() from exc
            raise UserError(friendly_message(exc), key) from exc
        if not info:
            raise NoMediaError()
        url = base_url

        container = self.container_pref
        entries: list[MediaEntry] = []
        if info.get("entries") is not None:
            for i, e in enumerate(info["entries"] or [], 1):
                if not e:
                    continue
                entry = entry_from_info(e, i, container)
                if not entry:
                    continue
                own_url = e.get("webpage_url") or ""
                if own_url.startswith(("http://", "https://")) and own_url != url:
                    entry.url = own_url  # kendi adresi olan öğe (ör. oynatma listesindeki video)
                else:
                    entry.url = url  # aynı gönderideki galeri: sıra numarasıyla indirilir
                    entry.playlist_index = i
                entries.append(entry)
        else:
            entry = entry_from_info(info, 1, container)
            if entry:
                entry.url = url
                entries.append(entry)
        if not entries:
            raise NoMediaError()

        extractor = str(info.get("extractor_key") or "")
        platform = "" if extractor in ("", "Generic") else extractor
        if requested_index and not (1 <= requested_index <= len(entries)):
            requested_index = None  # tweetteki gerçek öğe sayısıyla uyuşmuyorsa yok say
        return MediaInfo(
            source_url=url,
            title=info.get("title") or entries[0].title or urlsplit(url).hostname or "Medya",
            platform=platform,
            kind=entries[0].kind,
            entries=entries,
            requested_index=requested_index,
            duration=info.get("duration") or entries[0].duration,
            thumbnail=info.get("thumbnail") or entries[0].thumbnail,
            uploader=str(info.get("uploader") or info.get("channel") or ""),
        )

    # ------------------------------------------------------------ indirme
    def download(self, task: DownloadTask, progress: ProgressCallback, control: DownloadControl) -> Path:
        base, skip = resolve_base_name(task.out_dir, task.base_name, task.conflict)
        if skip:
            raise SkippedError(str(skip))
        fmt = task.fmt

        state = {"base_bytes": 0, "stage": "İndiriliyor"}

        def hook(d: dict[str, Any]) -> None:
            if control.is_set():
                raise CancelledError()
            status = d.get("status")
            if status == "downloading":
                done = int(d.get("downloaded_bytes") or 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                info = d.get("info_dict") or {}
                if info.get("vcodec") == "none" and fmt.is_merge:
                    state["stage"] = "Ses indiriliyor"
                elif fmt.is_merge:
                    state["stage"] = "Video indiriliyor"
                if fmt.is_merge and fmt.filesize:
                    overall_done = state["base_bytes"] + done
                    overall_total = max(fmt.filesize, overall_done)
                    percent = min(99.0, overall_done / overall_total * 100)
                    shown_done, shown_total = overall_done, overall_total
                else:
                    percent = (done / total * 100) if total else None
                    shown_done, shown_total = done, int(total) if total else None
                progress(
                    ProgressInfo(
                        status=state["stage"],
                        percent=percent,
                        done_bytes=shown_done,
                        total_bytes=shown_total,
                        speed=d.get("speed"),
                        eta=d.get("eta"),
                        filename=Path(d.get("filename") or "").name,
                        indeterminate=percent is None,
                    )
                )
            elif status == "finished":
                state["base_bytes"] += int(d.get("total_bytes") or d.get("downloaded_bytes") or 0)

        def pp_hook(d: dict[str, Any]) -> None:
            if d.get("status") == "started":
                name = d.get("postprocessor", "")
                text = {
                    "Merger": "Video ve ses birleştiriliyor",
                    "FFmpegExtractAudio": "Ses dönüştürülüyor",
                    "FFmpegVideoRemuxer": "Dosya hazırlanıyor",
                }.get(name, "İşleniyor")
                progress(ProgressInfo(status=text, indeterminate=True, filename=base))

        opts = build_download_opts(self._base_opts(), task, base, hook, pp_hook)

        try:
            result = None
            attempts = [opts["format"], *self._fallback_selectors(fmt)]
            for n, selector in enumerate(attempts):
                try:
                    with yt_dlp.YoutubeDL(opts | {"format": selector}) as ydl:
                        result = ydl.extract_info(task.url, download=True)
                    break
                except CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    # Seçili format indirme anında yok/erişilemez (YouTube format listesi istemciye göre değişir,
                    # tekil akışlar 403 verebilir): aynı çözünürlükte başka codec, sonra daha düşük kaliteyle dene.
                    if control.is_set() or n == len(attempts) - 1 or error_key(exc) not in ("format", "forbidden"):
                        raise
                    log.warning("format %r başarısız (%s), yedek seçici deneniyor", selector, error_key(exc))
                    self._cleanup(task.out_dir, base)
        except CancelledError:
            if not control.keep_partial:  # gerçek iptal: yarım dosyayı sil. Duraklatmada KORU (resume icin)
                self._cleanup(task.out_dir, base)
            raise
        except Exception as exc:  # noqa: BLE001
            if control.is_set():
                if not control.keep_partial:
                    self._cleanup(task.out_dir, base)
                raise CancelledError() from exc
            log.exception("yt-dlp indirme hatası: %s", task.url)
            key = error_key(exc)
            raise UserError(friendly_message(exc), key) from exc

        path = self._final_path(result, task.out_dir, base)
        progress(ProgressInfo(status="Tamamlandı", percent=100.0, filename=path.name if path else base))
        if not path:
            raise UserError.from_key("download_failed")
        return path

    @staticmethod
    def _fallback_selectors(fmt: MediaFormat) -> list[str]:
        """Seçilen format indirilemezse sırayla denenecek yedek yt-dlp seçicileri."""
        if fmt.kind != KIND_VIDEO or not fmt.height:
            return []
        h = int(fmt.height)
        return [
            f"bv*[height={h}]+ba/b[height={h}]",
            f"bv*[height<={h}]+ba/b[height<={h}]/b",
        ]

    @staticmethod
    def _final_path(result: Any, out_dir: Path, base: str) -> Optional[Path]:
        def find(info: Any) -> Optional[str]:
            if not isinstance(info, dict):
                return None
            for rd in info.get("requested_downloads") or []:
                if rd.get("filepath"):
                    return rd["filepath"]
            for e in info.get("entries") or []:
                found = find(e)
                if found:
                    return found
            return info.get("filepath")

        found = find(result)
        if found and Path(found).exists():
            return Path(found)
        candidates = [p for p in out_dir.glob("*") if p.stem == base and p.suffix not in (".part", ".ytdl")]
        return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None

    @staticmethod
    def _cleanup(out_dir: Path, base: str) -> None:
        """İptal sonrası yarım kalan geçici dosyaları temizler."""
        import glob

        for pattern in (f"{glob.escape(base)}*.part", f"{glob.escape(base)}*.ytdl", f"{glob.escape(base)}*.temp.*"):
            for p in out_dir.glob(pattern):
                try:
                    p.unlink()
                except OSError:
                    pass
