"""Sunucuyu başlatır:  python -m server  (GETLIYO_HOST / GETLIYO_PORT ile ayarlanır)."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn

from app.downloaders.http_utils import set_max_download_bytes
from app.utils.net_guard import allow_host, install_resolver_guard, set_public_only
from server.app import create_app
from server.config import Config


def _ensure_binaries() -> None:
    """FFmpeg/Deno yoksa (Windows'ta) ilk açılışta bin\\ klasörüne otomatik indirir."""
    if os.name != "nt" or os.environ.get("GETLIYO_AUTO_FETCH", "1") == "0":
        return
    script = Path(__file__).resolve().parents[1] / "scripts" / "fetch_ffmpeg.py"
    bin_dir = script.parents[1] / "bin"
    if not script.is_file() or all((bin_dir / n).is_file() for n in ("ffmpeg.exe", "ffprobe.exe", "deno.exe")):
        return
    print("FFmpeg/Deno bulunamadı, indiriliyor (yalnızca ilk açılışta)...")
    spec = importlib.util.spec_from_file_location("fetch_ffmpeg", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


def main() -> None:
    _ensure_binaries()
    config = Config.from_env()
    set_public_only(not config.allow_private_urls)  # her HTTP isteğinde (yönlendirmeler dahil) iç ağı engeller
    if config.proxy_url:  # yapılandırılmış çıkış proxy'sine bilerek izin ver
        allow_host(urlsplit(config.proxy_url).hostname or "")
    install_resolver_guard()  # yt-dlp ve DNS rebinding dahil tüm giden bağlantılar çözümleme anında denetlenir
    set_max_download_bytes(config.max_filesize_mb * 1024 * 1024)
    host = os.environ.get("GETLIYO_HOST", "127.0.0.1")
    port = int(os.environ.get("GETLIYO_PORT", "8000"))
    if not config.auth_required:
        print("Kimlik doğrulama KAPALI (GETLIYO_API_KEYS tanımlı değil) — yalnızca yerel kullanım için.")
        if host not in ("127.0.0.1", "localhost", "::1"):
            print(f"UYARI: sunucu {host} üzerinde anahtarsız dinliyor! İnternete açmadan önce GETLIYO_API_KEYS tanımla.")
    if not config.site_url:
        print("UYARI: GETLIYO_SITE_URL tanımlı değil; canonical/sitemap adresleri istekteki Host başlığından üretilir. Yayında tanımla.")
    print(f"Adres: http://{host}:{port}")
    uvicorn.run(create_app(config), host=host, port=port, proxy_headers=True, server_header=False, access_log=False)


if __name__ == "__main__":
    main()
