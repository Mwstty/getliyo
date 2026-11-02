"""getliyo — giriş noktası."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # `python app\main.py` ile çalıştırılırsa proje kökünü yola ekle
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.downloaders.manager import DownloaderManager
from app.history.db import HistoryDB
from app.media.ffmpeg_manager import FFmpegManager
from app.native.single_instance import SingleInstanceServer, forward_to_running_instance
from app.settings.settings_manager import SettingsManager
from app.ui.main_window import MainWindow
from app.ui.styles import apply_theme
from app.utils.logger import get_logger, setup_logging
from app.utils.paths import APP_NAME, cache_dir, resource_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--url", default="", help="Tarayıcı eklentisinden gelen bağlantı")
    args, _unknown = parser.parse_known_args(sys.argv[1:])
    return args


def _install_excepthook() -> None:
    log = get_logger("crash")

    def hook(exc_type, exc, tb) -> None:
        log.critical("Yakalanmamış hata", exc_info=(exc_type, exc, tb))
        if QApplication.instance():
            QMessageBox.critical(None, APP_NAME, "Beklenmeyen bir hata oluştu. Ayrıntılar log dosyasında.")

    sys.excepthook = hook


def main() -> int:
    # Installer kaldırma sırasında bunu çağırır: GUI açmadan, hızlıca temizlik yapıp çıkar.
    if "--uninstall-cleanup" in sys.argv:
        from app.utils.uninstall_cleanup import run_cleanup

        return run_cleanup(sys.argv[1:])

    setup_logging()
    _install_excepthook()
    if os.name == "nt":  # görev çubuğunda doğru simge
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("getliyo.app")
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    icon = resource_path("resources/icon.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    args = _parse_args()

    # Uygulama zaten açıksa: URL'yi ona ilet (varsa), kendisi hiç pencere açmadan çıksın.
    # Tarayıcı eklentisi her tıklamada bu programı yeniden başlatır; bu kontrol olmadan
    # her seferinde yeni bir pencere açılırdı.
    if forward_to_running_instance(args.url):
        return 0

    settings = SettingsManager()
    apply_theme(app, settings.get("theme"))  # Koyu / Açık / Sistem (spec madde 7)
    ffmpeg = FFmpegManager()
    manager = DownloaderManager(ffmpeg)

    # Bozuk config/klasör/veritabanı sessizce onarılır (spec madde 43); kullanıcı verisi kaybolmaz.
    from app.downloaders.http_utils import set_thumbnail_cache_dir

    set_thumbnail_cache_dir(cache_dir() / "thumbs")
    history = HistoryDB()

    window = MainWindow(settings, ffmpeg, manager, history)
    server = SingleInstanceServer(window.open_url)  # window canlı kaldığı sürece referans kalmalı
    window._single_instance_server = server  # noqa: SLF001 - GC'ye karşı referansı pencerede tut
    if args.url:
        window.open_url(args.url)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
