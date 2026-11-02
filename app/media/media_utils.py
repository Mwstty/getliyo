"""Biçimlendirme yardımcıları ve format seçim mantığı."""
from __future__ import annotations

import dataclasses
from typing import Optional

from app.downloaders.base_downloader import (
    KIND_AUDIO,
    KIND_IMAGE,
    KIND_VIDEO,
    MediaEntry,
    MediaFormat,
)

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "avif", "bmp"}
VIDEO_EXTS = {"mp4", "webm", "mkv", "mov", "m4v", "avi", "flv"}
AUDIO_EXTS = {"mp3", "m4a", "wav", "ogg", "opus", "flac", "aac"}

MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
    "image/bmp": "bmp",
    "image/svg+xml": "svg",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/quicktime": "mov",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/flac": "flac",
}


def format_size(size: Optional[float], estimated: bool = False) -> str:
    if not size or size <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    text = f"{value:.0f} {units[idx]}" if idx <= 2 and value >= 100 else f"{value:.1f} {units[idx]}"
    return ("~" if estimated else "") + text


def format_duration(seconds: Optional[float]) -> str:
    if not seconds or seconds <= 0:
        return "—"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_speed(bps: Optional[float]) -> str:
    return f"{format_size(bps)}/s" if bps else "—"


def format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def kind_label(kind: str) -> str:
    return {KIND_VIDEO: "Video", KIND_IMAGE: "Görsel", KIND_AUDIO: "Audio"}.get(kind, kind)


def best_resolution_text(entry: MediaEntry) -> str:
    for f in entry.formats:
        if f.kind in (KIND_VIDEO, KIND_IMAGE) and f.resolution:
            return f.resolution
    return "—"


def _video_formats(entry: MediaEntry) -> list[MediaFormat]:
    return [f for f in entry.formats if f.kind == KIND_VIDEO]


_CODEC_PREF = {"avc": "AVC", "vp9": "VP9", "av1": "AV1", "hevc": "HEVC"}


def pick_by_height(entry: MediaEntry, max_height: Optional[int], codec_pref: str = "") -> Optional[MediaFormat]:
    """max_height'a en yakın (aşmayan) videoyu seçer; formatlar zaten iyiden kötüye sıralı.
    codec_pref verilirse, o çözünürlükte tercih edilen codec varsa o seçilir."""
    videos = _video_formats(entry)
    if not videos:
        return None
    chosen = videos[-1]
    if max_height is None:
        chosen = videos[0]
    else:
        for f in videos:
            if (f.height or 0) <= max_height:
                chosen = f
                break
    want = _CODEC_PREF.get(codec_pref, "")
    if want:
        for f in videos:
            if f.height == chosen.height and f.codec.startswith(want):
                return f
    return chosen


def pick_audio(entry: MediaEntry, container: str) -> Optional[MediaFormat]:
    audios = [f for f in entry.formats if f.kind == KIND_AUDIO]
    for f in audios:
        if f.container == container:
            return f
    return audios[0] if audios else None


def pick_format(
    entry: MediaEntry,
    preset: str,
    default_quality: str = "best",
    default_audio: str = "mp3",
    codec_pref: str = "",
) -> Optional[MediaFormat]:
    """Hızlı seçim ve varsayılan kalite mantığı.

    preset: default | best | best_mp4 | h1080 | h720 | audio
    """
    if not entry.formats:
        return None
    if entry.kind == KIND_IMAGE:
        return entry.formats[0]
    if entry.kind == KIND_AUDIO or preset == "audio":
        return pick_audio(entry, default_audio) or entry.formats[0]

    if preset == "best":
        return pick_by_height(entry, None)
    if preset == "best_mp4":
        f = pick_by_height(entry, None)
        return dataclasses.replace(f, container="mp4") if f else None
    if preset == "h1080":
        f = pick_by_height(entry, 1080)
        return dataclasses.replace(f, container="mp4") if f else None
    if preset == "h720":
        f = pick_by_height(entry, 720)
        return dataclasses.replace(f, container="mp4") if f else None

    limit = None if default_quality == "best" else int(default_quality)
    return pick_by_height(entry, limit, codec_pref) or entry.formats[0]
