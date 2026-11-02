"""FFmpeg/ffprobe/Deno konumu ve durumu (uygulamayla birlikte paketlenmiş bin\\ klasörü)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.utils.logger import get_logger
from app.utils.paths import app_dir, project_root, resource_path

log = get_logger("ffmpeg")
_EXE = ".exe" if os.name == "nt" else ""


class FFmpegManager:
    """bin\\ klasöründeki ffmpeg/ffprobe/deno dosyalarını bulur."""

    def __init__(self) -> None:
        self._dir: Path | None = self._find_dir()

    @staticmethod
    def _candidates() -> list[Path]:
        return [app_dir() / "bin", resource_path("bin"), project_root() / "bin"]

    def _find_dir(self) -> Path | None:
        for folder in self._candidates():
            if (folder / f"ffmpeg{_EXE}").is_file():
                return folder
        found = shutil.which("ffmpeg")
        return Path(found).parent if found else None

    @property
    def directory(self) -> Path | None:
        return self._dir

    @property
    def ffmpeg_path(self) -> Path | None:
        return self._dir / f"ffmpeg{_EXE}" if self._dir else None

    @property
    def ffprobe_path(self) -> Path | None:
        if not self._dir:
            return None
        path = self._dir / f"ffprobe{_EXE}"
        return path if path.is_file() else None

    @property
    def deno_path(self) -> Path | None:
        """YouTube için gereken JavaScript çalışma zamanı (yt-dlp tarafından kullanılır)."""
        for folder in self._candidates():
            if (folder / f"deno{_EXE}").is_file():
                return folder / f"deno{_EXE}"
        found = shutil.which("deno")
        return Path(found) if found else None

    @property
    def is_available(self) -> bool:
        return self.ffmpeg_path is not None and self.ffmpeg_path.is_file()

    def version(self) -> str | None:
        """`ffmpeg -version` ilk satırı (güvenli argüman listesiyle, shell yok)."""
        if not self.is_available:
            return None
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.run(
                [str(self.ffmpeg_path), "-version"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=flags,
            )
            return out.stdout.splitlines()[0] if out.stdout else None
        except (OSError, subprocess.SubprocessError):
            log.exception("ffmpeg sürümü okunamadı")
            return None

    def status_text(self) -> str:
        if not self.is_available:
            return "BULUNAMADI — bin\\ffmpeg.exe eksik (scripts\\setup.bat çalıştır)"
        version = self.version() or "sürüm okunamadı"
        return f"Hazır — {version}"
