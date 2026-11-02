"""Ayar varsayılanları ve seçenek listeleri."""
from __future__ import annotations

import json
from typing import Any

from app.utils.paths import resource_path

QUALITY_OPTIONS: list[tuple[str, str]] = [
    ("best", "En iyi kalite"),
    ("2160", "2160p (4K)"),
    ("1440", "1440p (2K)"),
    ("1080", "1080p"),
    ("720", "720p"),
    ("480", "480p"),
    ("360", "360p"),
]
VIDEO_FORMAT_OPTIONS: list[tuple[str, str]] = [("mp4", "MP4"), ("mkv", "MKV"), ("webm", "WebM")]
AUDIO_FORMAT_OPTIONS: list[tuple[str, str]] = [
    ("mp3", "MP3"),
    ("m4a", "M4A"),
    ("wav", "WAV"),
    ("opus", "Opus"),
    ("flac", "FLAC"),
]
CONFLICT_OPTIONS: list[tuple[str, str]] = [
    ("new", "Yeni isim oluştur"),
    ("overwrite", "Üzerine yaz"),
    ("skip", "Atla"),
]
THEME_OPTIONS: list[tuple[str, str]] = [
    ("dark", "Koyu"),
    ("light", "Açık"),
    ("system", "Sistem"),
]
CONCURRENCY_OPTIONS: list[tuple[str, str]] = [("1", "1"), ("2", "2"), ("3", "3"), ("5", "5")]
SPEED_LIMIT_OPTIONS: list[tuple[str, str]] = [
    ("0", "Sınırsız"),
    ("1", "1 MB/s"),
    ("5", "5 MB/s"),
    ("10", "10 MB/s"),
    ("20", "20 MB/s"),
]
RETRY_BACKOFF_OPTIONS: list[tuple[str, str]] = [("3", "3 sn"), ("5", "5 sn"), ("10", "10 sn"), ("30", "30 sn")]
POST_COMPLETE_OPTIONS: list[tuple[str, str]] = [
    ("nothing", "Hiçbir şey yapma"),
    ("notify", "Bildirim göster"),
    ("open_folder", "Klasörü aç"),
    ("open_file", "Dosyayı aç"),
]

PROXY_OPTIONS: list[tuple[str, str]] = [("off", "Kapalı"), ("http", "HTTP"), ("https", "HTTPS"), ("socks5", "SOCKS5")]
COOKIE_BROWSER_OPTIONS: list[tuple[str, str]] = [("", "Kullanma"), ("chrome", "Chrome"), ("edge", "Edge"), ("firefox", "Firefox")]

BUILTIN_DEFAULTS: dict[str, Any] = {
    "download_dir": "",
    "default_quality": "best",
    "default_video_format": "mp4",
    "default_audio_format": "mp3",
    "conflict_behavior": "new",
    "naming_template": "{title}",
    "theme": "dark",
    "max_concurrent_downloads": "3",
    "speed_limit_mbps": "0",
    "retry_backoff_seconds": "5",
    "retry_max_attempts": 5,
    "use_recycle_bin": True,
    "notifications_enabled": True,
    "clipboard_detect_enabled": True,
    "clipboard_auto_analyze": False,
    "post_complete_action": "notify",
    "start_minimized_to_tray": False,
    "close_to_tray": False,
    # Eski "profil" değerleri: arayüzde gösterilmez, yalnızca settings.json üzerinden (ya da ileride
    # sunucu/web entegrasyonundan) değiştirilir.
    "codec_pref": "",
    "subtitle_langs": [],
    "subtitle_format": "srt",
    "embed_subs": False,
    "ytdlp_auto_check": True,
    "web_server_autostart": False,
    "web_server_port": 8765,
    "folder_by_platform": False,
    "folder_by_type": False,
    "folder_by_date": False,
    "embed_metadata": True,
    "embed_thumbnail": False,
    "proxy_type": "off",
    "proxy_host": "",
    "proxy_port": 0,
    "proxy_user": "",
    "proxy_password_enc": "",
    "cookies_browser": "",
    "advanced_convert_enabled": False,
    "advanced_convert_codec": "h264",
    "advanced_convert_container": "mp4",
    "advanced_convert_max_height": "0",
}

VALID: dict[str, set[str]] = {
    "default_quality": {k for k, _ in QUALITY_OPTIONS},
    "default_video_format": {k for k, _ in VIDEO_FORMAT_OPTIONS},
    "default_audio_format": {k for k, _ in AUDIO_FORMAT_OPTIONS},
    "conflict_behavior": {k for k, _ in CONFLICT_OPTIONS},
    "theme": {k for k, _ in THEME_OPTIONS},
    "max_concurrent_downloads": {k for k, _ in CONCURRENCY_OPTIONS},
    "speed_limit_mbps": {k for k, _ in SPEED_LIMIT_OPTIONS},
    "retry_backoff_seconds": {k for k, _ in RETRY_BACKOFF_OPTIONS},
    "post_complete_action": {k for k, _ in POST_COMPLETE_OPTIONS},
    "proxy_type": {k for k, _ in PROXY_OPTIONS},
    "cookies_browser": {k for k, _ in COOKIE_BROWSER_OPTIONS},
    "codec_pref": {"", "avc", "vp9", "av1", "hevc"},
    "subtitle_format": {"srt", "vtt", "ass"},
    "advanced_convert_codec": {"h264", "h265", "vp9", "av1"},
    "advanced_convert_container": {"mp4", "mkv", "webm"},
    "advanced_convert_max_height": {"0", "2160", "1440", "1080", "720", "480"},
}


def load_defaults() -> dict[str, Any]:
    """config/default_settings.json varsa onu, yoksa gömülü varsayılanları kullanır."""
    data = dict(BUILTIN_DEFAULTS)
    try:
        with open(resource_path("config/default_settings.json"), encoding="utf-8") as fh:
            loaded = json.load(fh)
        for key in BUILTIN_DEFAULTS:
            if key in loaded and (key not in VALID or loaded[key] in VALID[key]):
                data[key] = loaded[key]
    except (OSError, ValueError):
        pass
    return data
