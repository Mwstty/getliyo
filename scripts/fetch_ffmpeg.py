"""bin\\ klasörüne ffmpeg.exe, ffprobe.exe ve deno.exe indirir (Windows).

FFmpeg: gyan.dev "release essentials" (yedek: BtbN). Deno: yt-dlp'nin YouTube için
kullandığı JavaScript çalışma zamanı.
"""
from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
FFMPEG_URLS = [
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
]
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"


def download(url: str) -> bytes:
    print(f"  indiriliyor: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "getliyo-setup"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - sabit https adresleri
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        done = 0
        while chunk := resp.read(1 << 20):
            buf.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total}%  ", end="", flush=True)
        print()
        return buf.getvalue()


def extract(data: bytes, wanted: set[str]) -> set[str]:
    found: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            base = Path(name).name.lower()
            if base in wanted:
                (BIN / base).write_bytes(zf.read(name))
                found.add(base)
    return found


def ensure_ffmpeg() -> bool:
    if (BIN / "ffmpeg.exe").exists() and (BIN / "ffprobe.exe").exists():
        print("FFmpeg zaten var, atlaniyor.")
        return True
    for url in FFMPEG_URLS:
        try:
            if extract(download(url), {"ffmpeg.exe", "ffprobe.exe"}) == {"ffmpeg.exe", "ffprobe.exe"}:
                print("FFmpeg hazir.")
                return True
        except Exception as exc:  # noqa: BLE001
            print(f"  basarisiz: {exc}")
    return False


def ensure_deno() -> bool:
    if (BIN / "deno.exe").exists():
        print("Deno zaten var, atlaniyor.")
        return True
    try:
        if "deno.exe" in extract(download(DENO_URL), {"deno.exe"}):
            print("Deno hazir.")
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"  basarisiz: {exc}")
    return False


def main() -> int:
    BIN.mkdir(exist_ok=True)
    ok_ff = ensure_ffmpeg()
    ok_deno = ensure_deno()
    if not ok_ff:
        print("\nHATA: FFmpeg indirilemedi. Internetini kontrol edip tekrar dene ya da ffmpeg.exe ve ffprobe.exe dosyalarini elle bin\\ klasorune koy.")
        return 1
    if not ok_deno:
        print("\nUYARI: Deno indirilemedi; YouTube'da bazi formatlar eksik kalabilir. deno.exe'yi elle bin\\ klasorune koyabilirsin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
