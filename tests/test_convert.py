"""FFmpeg dönüştürme: gerçek ffmpeg ile (yoksa atlanır)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from app.downloaders.base_downloader import ConvertSpec, DownloadControl
from app.media.convert import build_args, compatible, convert_file, probe_duration

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="ffmpeg yok")


@pytest.fixture
def clip(tmp_path):
    out = tmp_path / "kaynak.mkv"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=15:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac", str(out)], check=True)
    return out


def test_compat_rules():
    assert compatible("vp9", "webm") and not compatible("h264", "webm") and compatible("h264", "mp4")


def test_build_args_no_shell_and_scale():
    a = build_args(Path("ffmpeg"), Path("a.mkv"), Path("b.mp4"), ConvertSpec("h264", "mp4", 1080))
    assert isinstance(a, list) and "libx264" in a and any("min(ih,1080)" in x for x in a)
    with pytest.raises(ValueError):
        build_args(Path("ffmpeg"), Path("a"), Path("b"), ConvertSpec("h264", "webm"))
    with pytest.raises(ValueError):
        build_args(Path("ffmpeg"), Path("a"), Path("b"), ConvertSpec("bilinmeyen", "mp4"))


@needs_ffmpeg
def test_mkv_to_mp4_h264_downscale(clip):
    events = []
    out = convert_file(Path(FFMPEG), Path(FFPROBE) if FFPROBE else None, clip, ConvertSpec("h264", "mp4", 240), events.append, DownloadControl())
    assert out.suffix == ".mp4" and out.exists() and not clip.exists(), "orijinal silinip yenisi kalmalı"
    dims = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height,codec_name",
                           "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert "h264" in dims and dims.endswith("240")
    assert probe_duration(Path(FFPROBE), out) > 1


@needs_ffmpeg
def test_mkv_to_webm_vp9(clip):
    out = convert_file(Path(FFMPEG), Path(FFPROBE), clip, ConvertSpec("vp9", "webm", None), lambda p: None, DownloadControl())
    assert out.suffix == ".webm" and out.stat().st_size > 0


@needs_ffmpeg
def test_cancel_removes_partial_output(clip):
    from app.utils.errors import CancelledError
    ctl = DownloadControl(); ctl.stop()
    with pytest.raises(CancelledError):
        convert_file(Path(FFMPEG), Path(FFPROBE), clip, ConvertSpec("h264", "mp4", None), lambda p: None, ctl)
    assert clip.exists(), "iptalde orijinal korunmalı"
    assert not list(clip.parent.glob("*.dönüştürülüyor.*"))
