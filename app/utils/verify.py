"""İndirme sonrası doğrulama (spec madde 38): dosya var mı, boyut >0 mı, ffprobe açabiliyor mu."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

log = get_logger("verify")


class VerifyResult:
    def __init__(self, ok: bool, reason: str = "") -> None:
        self.ok, self.reason = ok, reason

    def __bool__(self) -> bool:
        return self.ok


def verify_download(path: Path, kind: str, ffprobe: Optional[Path] = None) -> VerifyResult:
    """kind: video/audio/image. ffprobe verilmişse ve video/audio ise medya probe edilir."""
    try:
        if not path.is_file():
            return VerifyResult(False, "Dosya oluşturulamadı.")
        if path.stat().st_size <= 0:
            return VerifyResult(False, "Dosya boş (0 bayt).")
    except OSError:
        return VerifyResult(False, "Dosyaya erişilemiyor.")
    if kind in ("video", "audio") and ffprobe and ffprobe.is_file():
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.run(  # argüman listesi, shell yok
                [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=30, creationflags=flags,
            )
            if out.returncode != 0:
                log.warning("ffprobe başarısız: %s", out.stderr.strip()[:200])
                return VerifyResult(False, "Medya dosyası açılamadı (bozuk olabilir).")
        except (OSError, subprocess.SubprocessError):
            log.exception("ffprobe çalıştırılamadı")  # probe yapılamadıysa dosyayı suçlama
    elif kind == "image":
        try:
            from PIL import Image

            with Image.open(path) as im:
                im.verify()
        except Exception:  # noqa: BLE001 - AVIF vb. Pillow desteklemeyebilir, bu bozuk demek değil
            if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
                return VerifyResult(False, "Görsel dosyası açılamadı (bozuk olabilir).")
    return VerifyResult(True)
