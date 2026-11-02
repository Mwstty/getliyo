"""Native Messaging host: Chrome eklentisinden gelen URL'yi ana uygulamaya iletir.

Bu dosya ayrıca hafif, bağımsız bir EXE olarak derlenir (PyInstaller). Chrome her mesajda
bu programı başlatır, stdin'den bir mesaj okur, ana uygulamayı başlatır/uyarır ve çıkar.
Kasıtlı olarak PySide6/yt-dlp gibi ağır bağımlılıklara ihtiyaç duymaz -> hızlı açılır.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.native.protocol import ensure_binary_stdio, read_message, send_message


def _frozen_main_exe() -> Path | None:
    """Derlenmiş host, ana EXE ile aynı klasörde bulunur (installer/build.bat ikisini de kurar)."""
    candidate = Path(sys.executable).resolve().parent / "getliyo.exe"
    return candidate if candidate.is_file() else None


def _launch(url: str) -> None:
    frozen = getattr(sys, "frozen", False)
    if frozen:
        exe = _frozen_main_exe()
        if not exe:
            raise FileNotFoundError("getliyo.exe host'un yanında bulunamadı.")
        subprocess.Popen([str(exe), "--url", url], close_fds=True)
    else:
        root = Path(__file__).resolve().parents[1]
        subprocess.Popen(
            [sys.executable, "-m", "app.main", "--url", url], cwd=str(root), close_fds=True
        )


def main() -> None:
    ensure_binary_stdio()
    try:
        message = read_message()
    except Exception as exc:  # noqa: BLE001
        send_message({"ok": False, "error": f"Mesaj okunamadı: {exc}"})
        return
    if not message:
        return
    url = str(message.get("url") or "").strip()
    if not url:
        send_message({"ok": False, "error": "URL boş"})
        return
    try:
        _launch(url)
        send_message({"ok": True})
    except Exception as exc:  # noqa: BLE001
        send_message({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    main()
