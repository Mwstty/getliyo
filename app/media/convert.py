"""İndirme sonrası opsiyonel FFmpeg dönüştürme (Gelişmiş): 4K→1080p, WebM→MP4, MKV→MP4, codec değişimi."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional

from app.downloaders.base_downloader import ConvertSpec, DownloadControl, ProgressInfo
from app.utils.errors import CancelledError, UserError
from app.utils.logger import get_logger

log = get_logger("convert")

CODEC_LIBS = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9", "av1": "libaom-av1"}
CODEC_LABELS = [("h264", "H.264"), ("h265", "H.265"), ("vp9", "VP9"), ("av1", "AV1")]
CONTAINERS = ("mp4", "mkv", "webm")


def audio_codec_for(container: str) -> str:
    return "libopus" if container == "webm" else "aac"


def compatible(codec: str, container: str) -> bool:
    """WebM yalnızca VP9/AV1 taşır; MP4'te VP9/AV1 desteği oynatıcıya bağlı olduğundan H.264/H.265 önerilir."""
    if container == "webm":
        return codec in ("vp9", "av1")
    return True


def build_args(ffmpeg: Path, src: Path, dst: Path, spec: ConvertSpec) -> list[str]:
    if spec.codec not in CODEC_LIBS:
        raise ValueError(f"Bilinmeyen codec: {spec.codec}")
    if spec.container not in CONTAINERS or not compatible(spec.codec, spec.container):
        raise ValueError(f"{spec.codec} codec'i {spec.container} kapsayıcısıyla uyumsuz")
    args = [str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", str(src), "-map", "0:v:0?", "-map", "0:a?"]
    if spec.max_height:
        args += ["-vf", f"scale=-2:'min(ih,{int(spec.max_height)})'"]
    args += ["-c:v", CODEC_LIBS[spec.codec]]
    if spec.codec in ("h264", "h265"):
        args += ["-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p"]
    elif spec.codec == "vp9":
        args += ["-crf", "32", "-b:v", "0"]
    elif spec.codec == "av1":
        args += ["-crf", "35", "-b:v", "0", "-cpu-used", "6"]
    args += ["-c:a", audio_codec_for(spec.container), "-b:a", "160k"]
    if spec.container == "mp4":
        args += ["-movflags", "+faststart"]
    args += ["-progress", "pipe:1", "-nostats", str(dst)]
    return args


def probe_duration(ffprobe: Optional[Path], path: Path) -> Optional[float]:
    if not ffprobe or not ffprobe.is_file():
        return None
    try:
        out = subprocess.run(
            [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return float(out.stdout.strip()) if out.returncode == 0 and out.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def convert_file(
    ffmpeg: Path,
    ffprobe: Optional[Path],
    src: Path,
    spec: ConvertSpec,
    progress: Callable[[ProgressInfo], None],
    control: DownloadControl,
) -> Path:
    """src'yi dönüştürür, başarılıysa orijinali siler ve yeni dosyanın yolunu döndürür."""
    dst = src.with_name(f"{src.stem}.dönüştürülüyor.{spec.container}")
    final = src.with_suffix(f".{spec.container}")
    if final == src:  # aynı kapsayıcı: geçici dosyaya yazıp üzerine koyarız
        final = src
    duration = probe_duration(ffprobe, src)
    args = build_args(ffmpeg, src, dst, spec)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=flags)  # noqa: S603
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if control.is_set():
                proc.terminate()
                raise CancelledError()
            if line.startswith("out_time_us=") and duration:
                try:
                    done = int(line.split("=", 1)[1]) / 1_000_000
                    progress(ProgressInfo(status="Dönüştürülüyor", percent=min(99.0, done / duration * 100), filename=src.name))
                except ValueError:
                    pass
        code = proc.wait()
        err = proc.stderr.read() if proc.stderr else ""
    except BaseException:
        proc.kill()
        dst.unlink(missing_ok=True)
        raise
    if code != 0 or not dst.is_file() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        log.error("ffmpeg dönüştürme hatası: %s", err.strip()[:400])
        raise UserError("Video dönüştürülemedi. Orijinal dosya korundu.", "download_failed")
    if final != src:
        src.unlink(missing_ok=True)
    dst.replace(final)
    return final
