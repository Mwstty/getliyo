"""Masaüstü uygulamasının içinden yerel web sunucusunu başlatır/durdurur (arayüzden bağımsız)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from app.downloaders.manager import DownloaderManager
from app.utils.logger import get_logger
from app.utils.paths import appdata_dir

log = get_logger("webserver")
HOST = "127.0.0.1"  # yalnızca bu bilgisayar; dışarıya açmak için server/ paketini ayrıca çalıştır


class LocalServer:
    def __init__(self) -> None:
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self.port = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and bool(self._server and self._server.started)

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def start(self, manager: DownloaderManager, download_dir: Path, port: int, max_concurrent: int = 2) -> None:
        """Başlatır; port doluysa ya da açılamazsa RuntimeError (kullanıcıya gösterilebilir mesajla)."""
        if self.running:
            return
        import uvicorn

        from server.app import create_app
        from server.config import Config

        config = Config.local(appdata_dir() / "server", download_dir / "Web", max_concurrent)
        # log_config=None: pencereli (konsolsuz) EXE'de stdout olmadığı için uvicorn'un varsayılan log ayarı çöker
        server = uvicorn.Server(uvicorn.Config(create_app(config, manager), host=HOST, port=port,
                                               log_config=None, access_log=False, server_header=False))
        server.install_signal_handlers = lambda: None  # ana iş parçacığı dışında sinyal kurulamaz
        thread = threading.Thread(target=self._serve, args=(server,), name="web-server", daemon=True)
        thread.start()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if server.started:
                self._server, self._thread, self.port = server, thread, port
                log.info("Web sunucu başladı: %s", self.url)
                return
            if not thread.is_alive():
                break
            time.sleep(0.05)
        server.should_exit = True
        raise RuntimeError(f"Web sunucu başlatılamadı. {port} numaralı port başka bir uygulama tarafından kullanılıyor olabilir.")

    @staticmethod
    def _serve(server) -> None:
        try:
            server.run()
        except BaseException:  # noqa: BLE001 - bind hatası SystemExit olarak gelir
            log.exception("Web sunucu durdu")

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Web sunucu durduruldu")
        self._server = self._thread = None
