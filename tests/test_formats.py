from app.downloaders.ytdlp_downloader import build_formats, choose_container, codec_family, entry_from_info
from app.media.media_utils import format_duration, format_size, pick_format


def fmt(fid, vc, ac, h=None, fps=None, ext="mp4", tbr=1000, size=None, abr=None):
    return {"format_id": fid, "vcodec": vc, "acodec": ac, "height": h, "width": h and int(h * 16 / 9), "fps": fps, "ext": ext, "tbr": tbr, "filesize": size, "abr": abr}


YT = {
    "id": "abc",
    "title": "Test",
    "duration": 100,
    "formats": [
        {"format_id": "sb0", "ext": "mhtml", "vcodec": "none", "acodec": "none", "protocol": "mhtml"},
        fmt("140", "none", "mp4a.40.2", ext="m4a", tbr=129, size=1_000_000, abr=129),
        fmt("251", "none", "opus", ext="webm", tbr=140, size=1_100_000, abr=140),
        fmt("137", "avc1.640028", "none", 1080, 30, tbr=4000, size=50_000_000),
        fmt("248", "vp09.00.40.08", "none", 1080, 30, "webm", tbr=2500, size=30_000_000),
        fmt("399", "av01.0.08M.08", "none", 1080, 30, tbr=1500, size=20_000_000),
        fmt("136", "avc1.4d401f", "none", 720, 30, tbr=2000, size=25_000_000),
        fmt("18", "avc1.42001E", "mp4a.40.2", 360, 30, tbr=500, size=8_000_000),
    ],
}


def test_video_rows_sorted_and_merged():
    kind, formats = build_formats(YT)
    assert kind == "video"
    videos = [f for f in formats if f.kind == "video"]
    assert [f.height for f in videos] == sorted([f.height for f in videos], reverse=True)
    top = videos[0]
    assert top.height == 1080 and top.codec == "AVC" and top.is_merge
    assert top.selector == "137+140"  # mp4 için m4a ses tercih edilir
    assert top.filesize == 51_000_000
    prog = [f for f in videos if f.height == 360][0]
    assert not prog.is_merge and prog.selector == "18"
    assert not any("sb0" in f.selector for f in formats)


def test_no_missing_resolutions():
    _, formats = build_formats(YT)
    assert {f.height for f in formats if f.kind == "video"} == {1080, 720, 360}


def test_audio_rows():
    _, formats = build_formats(YT)
    audio = [f for f in formats if f.kind == "audio"]
    assert [f.container for f in audio] == ["mp3", "m4a", "wav", "opus", "flac"]
    assert all(f.needs_ffmpeg for f in audio)


def test_webm_container_fallback():
    assert choose_container("AVC", "webm") == "mkv"
    assert choose_container("VP9", "webm") == "webm"
    _, formats = build_formats(YT, "webm")
    top_avc = [f for f in formats if f.codec == "AVC" and f.height == 1080][0]
    assert top_avc.container == "mkv"


def test_image_entry():
    info = {"id": "1", "title": "Foto", "formats": [{"format_id": "0", "ext": "jpg", "url": "https://a/x.jpg", "width": 3840, "height": 2160, "vcodec": None, "acodec": None}]}
    e = entry_from_info(info, 1)
    assert e and e.kind == "image" and e.formats[0].resolution == "3840×2160" and e.formats[0].container == "jpg"


def test_audio_only_source():
    info = {"id": "s", "title": "Şarkı", "duration": 200, "formats": [fmt("a", "none", "mp3", ext="mp3", abr=128, size=3_000_000)]}
    kind, formats = build_formats(info)
    assert kind == "audio" and len(formats) == 5


def test_empty():
    assert build_formats({"formats": []}) == (None, [])


def test_pick_format():
    e = entry_from_info(YT, 1)
    assert pick_format(e, "best").height == 1080
    assert pick_format(e, "h720").height == 720 and pick_format(e, "h720").container == "mp4"
    assert pick_format(e, "default", "720").height == 720
    assert pick_format(e, "default", "144").height == 360  # en düşüğe düşer
    assert pick_format(e, "audio", default_audio="m4a").container == "m4a"


def test_codec_family():
    assert codec_family("avc1.640028") == "AVC"
    assert codec_family("vp09.00") == "VP9"
    assert codec_family("none") == ""


def test_helpers():
    assert format_size(3_650_000_000) == "3.4 GB"
    assert format_size(None) == "—"
    assert format_duration(3725) == "1:02:05"


def test_mixed_gallery_classification_instagram_reddit_style():
    """Instagram carousel / Reddit gallery: yt-dlp 'entries' listesinde foto+video karışık
    gelebilir. Her öğe KENDİ formatlarına göre siniflandirilmali, hicbiri zorla video
    sayilmamali (X /photo/N buguyla ayni kok sorun, ama burada dogrudan entry duzeyinde
    test ediyoruz)."""
    photo_entry = {"id": "p1", "title": "Foto 1", "formats": [
        {"format_id": "0", "ext": "jpg", "url": "https://a/p1.jpg", "width": 1080, "height": 1350, "vcodec": None, "acodec": None}
    ]}
    video_entry = {"id": "v1", "title": "Video 1", "duration": 12, "formats": [
        fmt("v", "avc1.4d001f", "mp4a.40.2", 720, 30, tbr=1500, size=6_000_000)
    ]}
    photo_entry2 = {"id": "p2", "title": "Foto 2", "formats": [
        {"format_id": "0", "ext": "png", "url": "https://a/p2.png", "width": 1920, "height": 1080, "vcodec": None, "acodec": None}
    ]}
    e1 = entry_from_info(photo_entry, 1)
    e2 = entry_from_info(video_entry, 2)
    e3 = entry_from_info(photo_entry2, 3)
    assert e1.kind == "image" and e1.formats[0].container == "jpg"
    assert e2.kind == "video" and e2.formats[0].container == "mp4"
    assert e3.kind == "image" and e3.formats[0].container == "png"
    # hicbiri diger turlerin formatlariyla kirlenmemis
    assert all(f.kind == "image" for f in e1.formats)
    assert all(f.kind == "video" or f.kind == "audio" for f in e2.formats)


# ---------------- Faz 2: genişletilmiş medya modeli ve indirme seçenekleri
def test_entry_details_subtitles_chapters_audio_tracks():
    info = {
        "id": "abc", "title": "Deneme", "duration": 100, "uploader": "Kanal", "extractor_key": "Youtube",
        "upload_date": "20260927", "description": "aciklama", "chapters": [{}, {}, {}],
        "subtitles": {"tr": [{}], "en": [{}], "live_chat": [{}]},
        "formats": [
            fmt("137", "avc1.640028", "none", 1080, 30, tbr=4000, size=50_000_000),
            {**fmt("140-tr", "none", "mp4a.40.2", ext="m4a", abr=128, size=1_000_000), "language": "tr"},
            {**fmt("140-en", "none", "mp4a.40.2", ext="m4a", abr=130, size=1_000_000), "language": "en"},
        ],
    }
    e = entry_from_info(info, 1)
    assert e.uploader == "Kanal" and e.upload_date == "2026-09-27" and e.chapters == 3
    assert e.subtitles == ["en", "tr"], "live_chat altyazı sayılmamalı"
    assert [t[0] for t in e.audio_tracks] == ["140-en", "140-tr"]
    assert e.formats[0].bitrate == 4000


def test_single_language_has_no_audio_track_choice():
    info = {"id": "a", "title": "t", "formats": [
        fmt("137", "avc1.640028", "none", 1080, 30, tbr=4000, size=50_000_000),
        {**fmt("140", "none", "mp4a.40.2", ext="m4a", abr=128, size=1_000_000), "language": "tr"}]}
    assert entry_from_info(info, 1).audio_tracks == []


def test_codec_preference():
    e = entry_from_info(YT, 1)
    assert pick_format(e, "default", "1080").codec == "AVC"  # sıralamadaki ilk
    assert pick_format(e, "default", "1080", codec_pref="vp9").codec == "VP9"
    assert pick_format(e, "default", "1080", codec_pref="av1").codec == "AV1"
    assert pick_format(e, "default", "720", codec_pref="vp9").codec == "AVC"  # 720p'de VP9 yok -> düşer


def test_download_opts_video_with_subs_metadata_proxy(tmp_path):
    from app.downloaders.base_downloader import DownloadTask
    from app.downloaders.ytdlp_downloader import build_download_opts
    e = entry_from_info(YT, 1)
    task = DownloadTask("t", "https://y", e.formats[0], tmp_path, "isim", subtitle_langs=["tr", "en"], subtitle_format="vtt",
                        embed_subs=True, embed_thumbnail=True, rate_limit_bps=1_000_000, proxy_url="socks5://u:p@h:1080",
                        cookies_browser="firefox", max_retries=7)
    o = build_download_opts({"quiet": True}, task, "isim")
    assert o["writesubtitles"] and o["subtitleslangs"] == ["tr", "en"] and o["subtitlesformat"] == "vtt/best"
    keys = [p["key"] for p in o["postprocessors"]]
    assert keys == ["FFmpegSubtitlesConvertor", "FFmpegEmbedSubtitle", "FFmpegMetadata", "EmbedThumbnail"]
    assert o["merge_output_format"] == "mp4" and o["ratelimit"] == 1_000_000 and o["retries"] == 7
    assert o["proxy"] == "socks5://u:p@h:1080" and o["cookiesfrombrowser"] == ("firefox",)
    assert o["writethumbnail"] and o["retry_sleep_functions"]["http"](0) in (3, 5)


def test_download_opts_audio_and_defaults(tmp_path):
    from app.downloaders.base_downloader import DownloadTask
    from app.downloaders.ytdlp_downloader import build_download_opts
    e = entry_from_info(YT, 1)
    audio = [f for f in e.formats if f.kind == "audio" and f.container == "flac"][0]
    o = build_download_opts({}, DownloadTask("t", "u", audio, tmp_path, "a"), "a")
    assert o["postprocessors"][0]["key"] == "FFmpegExtractAudio" and o["postprocessors"][0]["preferredcodec"] == "flac"
    assert "writesubtitles" not in o and "ratelimit" not in o and "proxy" not in o and "cookiesfrombrowser" not in o
    assert o["postprocessors"][-1]["key"] == "FFmpegMetadata"  # chapters/metadata varsayılan açık
