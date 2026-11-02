"""Ana pencere: sol gezinme (Ana Sayfa/İndirmeler/Geçmiş/Favoriler/Hata Merkezi) + Ayarlar."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QApplication,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.downloaders.base_downloader import KIND_VIDEO, ConvertSpec, DownloadTask, MediaEntry, MediaFormat, MediaInfo
from app.downloaders.manager import DownloaderManager
from app.history.db import HistoryDB
from app.history.models import STATUS_CANCELLED, STATUS_COMPLETED, STATUS_FAILED
from app.history.service import HistoryService
from app.media.ffmpeg_manager import FFmpegManager
from app.media.media_utils import format_size, pick_format
from app.server_control import LocalServer
from app.settings.settings_manager import SettingsManager
from app.ui.dialogs import BatchUrlDialog, StatsDialog, ask_close_with_active, ask_duplicate
from app.ui.download_widget import DownloadWidget, reveal_in_folder
from app.ui.error_center import ErrorCenterView
from app.ui.format_table import FormatTable, GalleryTable
from app.ui.history_view import HistoryView
from app.ui.media_card import MediaCard
from app.ui.nav_rail import NavRail
from app.ui.notifier import Notifier
from app.ui.settings_window import SettingsWindow
from app.ui.styles import apply_theme
from app.ui.workers import FunctionWorker
from app.utils.errors import UserError
from app.utils.filename import max_stem_length
from app.utils.folders import organized_dir
from app.utils.logger import get_logger
from app.utils.name_template import render_template
from app.utils.paths import cache_dir, resource_path
from app.utils.url_extract import clipboard_candidate, is_supported_url, parse_urls
from app.utils.validators import validate_url
from app.utils.ytdlp_update import check_ytdlp

log = get_logger("ui")

PRESETS = [
    ("EN İYİ KALİTE", "best"),
    ("EN İYİ / MP4", "best_mp4"),
    ("1080p / MP4", "h1080"),
    ("720p / MP4", "h720"),
    ("SADECE SES", "audio"),
]


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: SettingsManager,
        ffmpeg: FFmpegManager,
        manager: DownloaderManager,
        history: Optional[HistoryDB] = None,
    ) -> None:
        super().__init__()
        self.settings, self.ffmpeg, self.manager = settings, ffmpeg, manager
        self.history = history or HistoryDB()
        self.hist_service = HistoryService(self.history, protected_roots=[cache_dir().parent])
        self.info: Optional[MediaInfo] = None
        self._workers: set[FunctionWorker] = set()
        self._closing = False
        self.analyze_pool = QThreadPool()
        self.analyze_pool.setMaxThreadCount(2)
        self.download_pool = QThreadPool()
        self.download_pool.setMaxThreadCount(int(self.settings.get("max_concurrent_downloads")))
        self.manager.set_container_preference(settings.get("default_video_format"))
        self.manager.set_network(self._resolved_proxy_url(), settings.get("cookies_browser"))

        self.setWindowTitle("getliyo")
        self.setAcceptDrops(True)
        self.resize(1180, 860)
        self.setMinimumSize(940, 640)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.nav = NavRail()
        self.nav.page_selected.connect(self._goto_page)
        self.nav.settings_requested.connect(self._open_settings)
        outer.addWidget(self.nav)

        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)

        self.web_server = LocalServer()
        self._build_home_page()
        self._build_downloads_page()
        self.history_view = HistoryView(self.history, self.hist_service, self.settings, favorites_only=False)
        self.history_view.redownload_requested.connect(self.open_url)
        self.pages.addWidget(self.history_view)
        self.favorites_view = HistoryView(self.history, self.hist_service, self.settings, favorites_only=True)
        self.favorites_view.redownload_requested.connect(self.open_url)
        self.pages.addWidget(self.favorites_view)
        self.error_view = ErrorCenterView(self.history)
        self.error_view.retry_requested.connect(self.open_url)
        self.pages.addWidget(self.error_view)
        self.pages.setCurrentWidget(self.home_page)

        self._setup_shortcuts()
        self._setup_clipboard_watcher()
        icon_path = resource_path("resources/icon.ico")
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
        self.notifier = Notifier(self.settings, icon, self._restore_from_tray, self._quit_from_tray)
        if self.notifier.available and self.settings.get("start_minimized_to_tray"):
            self.notifier.show_tray()
        else:
            self.notifier.show_tray() if self.notifier.available else None

        if not ffmpeg.is_available:
            self._set_status("FFmpeg bulunamadı: video+ses birleştirme ve ses dönüştürme çalışmaz (Ayarlar > Sistem).", error=True)

        QTimer.singleShot(400, self._check_crash_recovery)
        QTimer.singleShot(2500, self._auto_check_ytdlp)
        if self.settings.get("web_server_autostart"):
            QTimer.singleShot(1000, lambda: self._start_web_server(open_browser=False))

    # ------------------------------------------------------------------ Ana Sayfa
    def _build_home_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 28, 36, 20)
        layout.setSpacing(14)

        title = QLabel("Ne indirmek istiyorsun?")
        title.setObjectName("hero")
        hint = QLabel("Bağlantıyı yapıştır, sürükle-bırak ya da panodan otomatik yakalansın.")
        hint.setObjectName("subtitle")
        head = QVBoxLayout()
        head.setSpacing(2)
        head.addWidget(title)
        head.addWidget(hint)
        batch_btn = QPushButton("Toplu URL")
        batch_btn.clicked.connect(self._open_batch_dialog)
        stats_btn = QPushButton("İstatistikler")
        stats_btn.clicked.connect(self._open_stats)
        top = QHBoxLayout()
        top.addLayout(head, 1)
        self.web_open_btn = QPushButton("Tarayıcıda aç")
        self.web_open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.web_server.url)))
        self.web_open_btn.hide()
        self.web_btn = QPushButton("Web sunucuyu başlat")
        self.web_btn.setToolTip("Bu bilgisayarda indirme sitesini açar (yalnızca bu bilgisayardan erişilir)")
        self.web_btn.clicked.connect(self._toggle_web_server)
        top.addWidget(self.web_open_btn, 0, Qt.AlignTop)
        top.addWidget(self.web_btn, 0, Qt.AlignTop)
        top.addWidget(batch_btn, 0, Qt.AlignTop)
        top.addWidget(stats_btn, 0, Qt.AlignTop)
        layout.addLayout(top)

        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("url")
        self.url_edit.setPlaceholderText("https://...")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self._analyze)
        self.analyze_btn = QPushButton("Analiz et")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.clicked.connect(self._analyze)
        self.quick_btn = QPushButton("Hızlı indir")
        self.quick_btn.setToolTip("Analiz eder, ayarlardaki varsayılan formatı seçip hemen indirir (Ctrl+Enter)")
        self.quick_btn.clicked.connect(self._quick_download)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.url_edit, 1)
        row.addWidget(self.analyze_btn)
        row.addWidget(self.quick_btn)
        layout.addLayout(row)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setFixedHeight(4)
        self.busy.hide()
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.busy)
        layout.addWidget(self.status)

        self.result = QFrame()
        rl = QVBoxLayout(self.result)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)
        self.card = MediaCard()
        rl.addWidget(self.card)

        self.chips = QWidget()
        cl = QHBoxLayout(self.chips)
        cl.setContentsMargins(0, 0, 0, 0)
        chip_title = QLabel("HIZLI SEÇİM")
        chip_title.setObjectName("section")
        cl.addWidget(chip_title)
        for label, preset in PRESETS:
            b = QPushButton(label)
            b.setObjectName("chip")
            b.clicked.connect(lambda _=False, p=preset: self._apply_preset(p))
            cl.addWidget(b)
        cl.addStretch(1)
        rl.addWidget(self.chips)

        self.format_table = FormatTable()
        self.format_table.selection_changed.connect(self._on_manual_select)
        self.gallery_table = GalleryTable()
        self.gallery_table.selection_changed.connect(self._update_download_button)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.format_table)
        self.stack.addWidget(self.gallery_table)
        self.stack.setMinimumHeight(190)
        rl.addWidget(self.stack, 1)

        self.select_all = QCheckBox("Tümünü seç")
        self.select_all.setChecked(True)
        self.select_all.toggled.connect(lambda checked: self._active_table().set_all(checked))
        none_btn = QPushButton("Hiçbirini Seçme")
        none_btn.clicked.connect(lambda: self._active_table().set_all(False))
        self.download_btn = QPushButton("İNDİR")
        self.download_btn.setObjectName("primary")
        self.download_btn.clicked.connect(self._download)
        bar = QHBoxLayout()
        bar.addWidget(self.select_all)
        bar.addWidget(none_btn)
        bar.addStretch(1)
        bar.addWidget(self.download_btn)
        rl.addLayout(bar)
        self.result.hide()
        layout.addWidget(self.result, 1)

        self.recent = QWidget()
        self.recent_layout = QVBoxLayout(self.recent)
        self.recent_layout.setContentsMargins(0, 8, 0, 0)
        self.recent_layout.setSpacing(6)
        layout.addWidget(self.recent)
        layout.addStretch(1)
        self._refresh_recent()
        self.pages.addWidget(page)
        self.home_page = page

    # ------------------------------------------------------------------ İndirmeler sayfası
    def _build_downloads_page(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 18)
        layout.setSpacing(12)

        title = QLabel("İNDİRMELER")
        title.setObjectName("title")
        layout.addWidget(title)

        self.dl_container = QWidget()
        self.dl_container.setObjectName("root")
        self.dl_layout = QVBoxLayout(self.dl_container)
        self.dl_layout.setContentsMargins(0, 0, 0, 0)
        self.dl_layout.setSpacing(8)
        self.dl_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.dl_container)
        scroll.viewport().setStyleSheet("background: transparent;")
        layout.addWidget(scroll, 1)
        self.empty_downloads_label = QLabel("Henüz aktif indirme yok. Ana Sayfa'dan bir bağlantı analiz et.")
        self.empty_downloads_label.setObjectName("muted")
        self.empty_downloads_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_downloads_label)
        self._update_empty_downloads_label()

        self.folder_label = QLabel()
        self.folder_label.setObjectName("muted")
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        change = QPushButton("KLASÖRÜ DEĞİŞTİR")
        change.clicked.connect(self._change_folder)
        open_btn = QPushButton("KLASÖRÜ AÇ")
        open_btn.clicked.connect(self._open_folder)
        footer = QHBoxLayout()
        footer.addWidget(self.folder_label, 1)
        footer.addWidget(change)
        footer.addWidget(open_btn)
        layout.addLayout(footer)
        self._refresh_folder_label()
        self.pages.addWidget(page)
        self.downloads_page = page

    # ------------------------------------------------------------------ navigasyon
    def _goto_page(self, key: str) -> None:
        mapping = {
            "home": self.home_page,
            "downloads": self.downloads_page,
            "history": self.history_view,
            "favorites": self.favorites_view,
            "errors": self.error_view,
        }
        self.pages.setCurrentWidget(mapping[key])
        if key == "home" and not self.result.isVisible():
            self.recent.show()

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+H"), self, activated=lambda: self.nav.select("history"))
        QShortcut(QKeySequence("Ctrl+J"), self, activated=lambda: self.nav.select("downloads"))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._quick_download)
        # Ctrl+V, QLineEdit'in kendi yerleşik yapıştırma davranışıyla zaten çalışır; ayrıca
        # bir kısayol tanımlamaya gerek yok.

    # ------------------------------------------------------------------ sürükle-bırak (madde 25)
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls: list[str] = []
        for u in event.mimeData().urls():
            local = u.toLocalFile()
            if local and local.lower().endswith((".txt", ".csv", ".list")):
                from app.ui.dialogs import read_urls_from_file

                urls += read_urls_from_file(local)
            elif u.toString().startswith(("http://", "https://")):
                urls.append(u.toString())
        if not urls and event.mimeData().hasText():
            urls = parse_urls(event.mimeData().text())
        event.acceptProposedAction()
        if not urls:
            return
        if len(urls) == 1:
            self.nav.select("home")
            self.open_url(urls[0])
        else:
            self._enqueue_batch(urls)

    # ------------------------------------------------------------------ panodan URL algılama (madde 24, 67)
    def _setup_clipboard_watcher(self) -> None:
        self._last_clipboard = ""
        self._clip_timer = QTimer(self)
        self._clip_timer.timeout.connect(self._check_clipboard)
        self._clip_timer.start(1500)

    def _check_clipboard(self) -> None:
        if not self.settings.get("clipboard_detect_enabled") or not self.isActiveWindow():
            return
        text = QGuiApplication.clipboard().text()
        if text == self._last_clipboard:
            return
        self._last_clipboard = text
        url = clipboard_candidate(text)
        if not url or url == self.url_edit.text():
            return
        if self.settings.get("clipboard_auto_analyze"):
            self.nav.select("home")
            self.open_url(url)
        else:
            self.notifier.notify("Bağlantı algılandı", url, on_click=lambda u=url: self.open_url(u))
            self._set_status(f"Panoda desteklenen bir bağlantı algılandı: {url}")

    # ------------------------------------------------------------------ crash recovery (madde 39)
    def _check_crash_recovery(self) -> None:
        stale = self.history.stale_downloads()
        if not stale:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Yarım kalan indirmeler")
        box.setText(f"Önceki oturumda {len(stale)} indirme yarım kaldı.")
        resume = box.addButton("Geçmişte İşaretle ve Temizle", QMessageBox.AcceptRole)
        box.addButton("Daha Sonra", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is resume:
            self.hist_service.discard_stale(stale)
            self._set_status(f"{len(stale)} yarım kalan indirme temizlendi.")

    # ------------------------------------------------------------------ yardımcılar
    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.setText(text)
        self.status.setProperty("error", "true" if error else "false")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def _refresh_folder_label(self) -> None:
        self.folder_label.setText(f"İndirme klasörü:  {self.settings.download_dir}")

    def _resolved_proxy_url(self) -> str:
        if self.settings.get("proxy_type") == "off" or not self.settings.get("proxy_host"):
            return ""
        from app.utils.secret import unprotect

        scheme = self.settings.get("proxy_type")
        host, port = self.settings.get("proxy_host"), self.settings.get("proxy_port")
        user = self.settings.get("proxy_user")
        pw = unprotect(self.settings.get("proxy_password_enc")) if self.settings.get("proxy_password_enc") else ""
        auth = f"{user}:{pw}@" if user else ""
        return f"{scheme}://{auth}{host}:{port}" if port else ""

    def _open_settings(self) -> None:
        if SettingsWindow(self.settings, self.ffmpeg, self.history, self).exec():
            self.manager.set_container_preference(self.settings.get("default_video_format"))
            self.manager.set_network(self._resolved_proxy_url(), self.settings.get("cookies_browser"))
            self.download_pool.setMaxThreadCount(int(self.settings.get("max_concurrent_downloads")))
            apply_theme(QApplication.instance(), self.settings.get("theme"))
            self._refresh_folder_label()

    def _change_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "İndirme klasörü", str(self.settings.download_dir))
        if not chosen:
            return
        from app.utils.path_check import validate_download_dir

        ok, msg = validate_download_dir(chosen)
        if not ok:
            QMessageBox.warning(self, "Klasör seçilemedi", msg)
            return
        self.settings.set("download_dir", chosen)
        self._refresh_folder_label()

    def _open_folder(self) -> None:
        folder = self.settings.download_dir
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            self._set_status("İndirme klasörü oluşturulamadı.", error=True)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _open_batch_dialog(self) -> None:
        dlg = BatchUrlDialog(self)
        if dlg.exec():
            self._enqueue_batch(dlg.urls)

    def _open_stats(self) -> None:
        StatsDialog(self.history.stats(), self).exec()

    def _refresh_recent(self) -> None:
        """Ana sayfanın altındaki 'Son indirilenler' listesi (en fazla 5 tamamlanmış kayıt)."""
        while self.recent_layout.count():
            item = self.recent_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        heading = QLabel("SON İNDİRİLENLER")
        heading.setObjectName("section")
        self.recent_layout.addWidget(heading)
        try:
            records = self.history.list(statuses=(STATUS_COMPLETED,), limit=5)
        except Exception:  # noqa: BLE001 - ana sayfa, geçmiş okunamasa da açılmalı
            log.exception("Son indirilenler okunamadı")
            records = []
        if not records:
            empty = QLabel("Henüz tamamlanmış indirme yok.")
            empty.setObjectName("muted")
            self.recent_layout.addWidget(empty)
            return
        for rec in records:
            title = rec.title if len(rec.title) <= 80 else rec.title[:77] + "..."
            size = format_size(rec.file_size) if rec.file_size else ""
            meta = "  ·  ".join(x for x in (rec.platform, rec.resolution, size) if x)
            btn = QPushButton(f"{title}\n{meta}" if meta else title)
            btn.setObjectName("recent")
            btn.setToolTip("Dosyanın bulunduğu klasörü aç")
            btn.clicked.connect(lambda _=False, p=rec.file_path: reveal_in_folder(Path(p)))
            self.recent_layout.addWidget(btn)

    # ------------------------------------------------------------------ yerel web sunucu
    def _toggle_web_server(self) -> None:
        if self.web_server.running:
            self._stop_web_server()
        else:
            self._start_web_server(open_browser=True)

    def _start_web_server(self, open_browser: bool) -> None:
        try:
            self.web_server.start(
                self.manager, self.settings.download_dir, int(self.settings.get("web_server_port")),
                int(self.settings.get("max_concurrent_downloads")),
            )
        except Exception as exc:  # noqa: BLE001 - port dolu, modül eksik vb.
            log.exception("Web sunucu başlatılamadı")
            self._set_status(str(exc) if isinstance(exc, RuntimeError) else "Web sunucu başlatılamadı.", error=True)
            return
        self._refresh_web_buttons()
        self._set_status(f"Web sunucu açık: {self.web_server.url}")
        if open_browser:
            QDesktopServices.openUrl(QUrl(self.web_server.url))

    def _stop_web_server(self) -> None:
        self.web_server.stop()
        self._refresh_web_buttons()
        self._set_status("Web sunucu durduruldu.")

    def _refresh_web_buttons(self) -> None:
        on = self.web_server.running
        self.web_btn.setText("Web sunucuyu durdur" if on else "Web sunucuyu başlat")
        self.web_open_btn.setVisible(on)

    def _close_services(self) -> None:
        self.web_server.stop()
        self.history.close()

    def _auto_check_ytdlp(self) -> None:
        """Her açılışta arka planda yt-dlp sürümünü kontrol eder; yeni sürüm varsa haber verir."""
        if not self.settings.get("ytdlp_auto_check"):
            return
        worker = FunctionWorker(check_ytdlp)
        worker.signals.result.connect(self._on_ytdlp_checked)
        worker.signals.error.connect(lambda m: log.info("yt-dlp kontrolü başarısız: %s", m))
        worker.signals.finished.connect(lambda w=worker: self._workers.discard(w))
        self._workers.add(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_ytdlp_checked(self, status) -> None:
        if status.latest is None:
            log.info("yt-dlp sürümü alınamadı (internet yok olabilir)")
            return
        if status.newer:
            msg = f"yt-dlp güncellemesi var: {status.current} → {status.latest}. İndirmeler bozulursa uygulamayı güncelle."
            log.info(msg)
            self._set_status(msg)
            self.notifier.notify("yt-dlp güncellemesi", f"{status.current} → {status.latest}")
        else:
            log.info("yt-dlp güncel (%s)", status.current)

    # ------------------------------------------------------------------ dış çağrı (tarayıcı eklentisi vb.)
    def open_url(self, url: str) -> None:
        """Eklentiden/komut satırından/Geçmiş-Tekrar İndir'den gelen URL'yi analiz eder, pencereyi öne getirir."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.nav.select("home")
        url = (url or "").strip()
        if not url:
            return
        self.url_edit.setText(url)
        self._analyze()

    def _enqueue_batch(self, urls: list[str]) -> None:
        """Toplu URL: her biri arka planda analiz edilip profildeki varsayılan format otomatik indirilir."""
        if not urls:
            return
        self.nav.select("downloads")
        for u in urls:
            worker = FunctionWorker(self.manager.analyze, u)
            worker.signals.result.connect(lambda info: self._auto_download_all(info))
            worker.signals.error.connect(lambda m, url=u: self._set_status(f"{url}: {m}", error=True))
            worker.signals.finished.connect(lambda w=worker: self._workers.discard(w))
            self._workers.add(worker)
            self.analyze_pool.start(worker)
        self._set_status(f"{len(urls)} bağlantı kuyruğa alınıp analiz ediliyor...")

    def _auto_download_all(self, info: MediaInfo) -> None:
        for entry in info.entries:
            fmt = self._pick_default(entry)
            if fmt:
                self._start_download(info, entry, fmt)

    # ------------------------------------------------------------------ analiz
    def _analyze(self) -> None:
        try:
            url = validate_url(self.url_edit.text())
        except UserError as exc:
            self._set_status(exc.message, error=True)
            return
        if not is_supported_url(url):
            log.info("Desteklenmeyen/bilinmeyen bağlantı denendi: analiz yine de deneniyor")
        self.url_edit.setText(url)
        self.analyze_btn.setEnabled(False)
        self.quick_btn.setEnabled(False)
        self.busy.show()
        self.result.hide()
        self.recent.hide()
        self.info = None
        self._set_status("Analiz ediliyor...")
        worker = FunctionWorker(self.manager.analyze_with_thumbnail, url)
        worker.signals.result.connect(self._on_analyzed)
        worker.signals.error.connect(lambda m: self._set_status(m, error=True))
        worker.signals.finished.connect(lambda w=worker: self._analysis_done(w))
        self._workers.add(worker)
        self.analyze_pool.start(worker)

    def _quick_download(self) -> None:
        """URL → analiz → profildeki varsayılan formatı otomatik seç → indir (madde 8)."""
        try:
            url = validate_url(self.url_edit.text())
        except UserError as exc:
            self._set_status(exc.message, error=True)
            return
        self.url_edit.setText(url)
        self.analyze_btn.setEnabled(False)
        self.quick_btn.setEnabled(False)
        self.busy.show()
        self._set_status("Hızlı indiriliyor...")
        worker = FunctionWorker(self.manager.analyze, url)
        worker.signals.result.connect(self._on_quick_analyzed)
        worker.signals.error.connect(lambda m: self._set_status(m, error=True))
        worker.signals.finished.connect(lambda w=worker: self._analysis_done(w))
        self._workers.add(worker)
        self.analyze_pool.start(worker)

    def _on_quick_analyzed(self, info: MediaInfo) -> None:
        self.info = info
        self._auto_download_all(info)
        self.nav.select("downloads")
        self._set_status(f"{info.title} — hızlı indirme başlatıldı.")

    def _analysis_done(self, worker: FunctionWorker) -> None:
        self.analyze_btn.setEnabled(True)
        self.quick_btn.setEnabled(True)
        self.busy.hide()
        self._workers.discard(worker)
        if not self.result.isVisible():
            self.recent.show()

    def _pick_default(self, entry: MediaEntry) -> Optional[MediaFormat]:
        return pick_format(
            entry, "default", self.settings.get("default_quality"),
            self.settings.get("default_audio_format"), self.settings.get("codec_pref"),
        )

    def _on_analyzed(self, info: MediaInfo) -> None:
        self.info = info
        self.card.set_info(info)
        if info.is_gallery:
            self.gallery_table.set_entries(info.entries, self._pick_default, info.requested_index)
            self.select_all.blockSignals(True)
            self.select_all.setChecked(not info.requested_index)
            self.select_all.blockSignals(False)
            self.select_all.show()
            self.chips.hide()
            self.stack.setCurrentWidget(self.gallery_table)
            if info.requested_index:
                self._set_status(
                    f"Bu gönderide {len(info.entries)} medya var — bağlantıdaki {info.requested_index}. öğe "
                    "işaretlendi, istersen diğerlerini de seçebilirsin."
                )
            else:
                self._set_status(f"{len(info.entries)} medya bulundu. İstediklerini işaretle.")
        else:
            entry = info.entries[0]
            self.format_table.set_formats(entry.formats)
            self.format_table.preselect(self._pick_default(entry))
            self.select_all.blockSignals(True)
            self.select_all.setChecked(False)
            self.select_all.blockSignals(False)
            self.select_all.show()
            self.chips.setVisible(entry.kind == KIND_VIDEO)
            self.stack.setCurrentWidget(self.format_table)
            self._set_status(
                "Analiz tamamlandı. Varsayılan format işaretlendi — istersen birden fazla format "
                "(ör. hem video hem ses) seçip hepsini birlikte indirebilirsin."
            )
        self.result.show()
        self.recent.hide()
        self._update_download_button()

    # ------------------------------------------------------------------ seçim
    def _active_table(self):
        return self.gallery_table if (self.info and self.info.is_gallery) else self.format_table

    def _apply_preset(self, preset: str) -> None:
        if not self.info or self.info.is_gallery:
            return
        fmt = pick_format(self.info.entries[0], preset, self.settings.get("default_quality"), self.settings.get("default_audio_format"))
        if not fmt:
            return
        self.format_table.preselect(fmt)
        self._update_download_button()

    def _on_manual_select(self) -> None:
        self._update_download_button()

    def _update_download_button(self) -> None:
        if not self.info:
            return
        if self.info.is_gallery:
            n = len(self.gallery_table.checked_entries())
        else:
            n = len(self.format_table.checked_formats())
        self.download_btn.setText("SEÇİLENİ İNDİR" if n == 1 else "SEÇİLENLERİ İNDİR")
        self.download_btn.setEnabled(n > 0)

    # ------------------------------------------------------------------ indirme
    def _make_task(self, info: MediaInfo, entry: MediaEntry, fmt: MediaFormat, disambiguate: bool = False) -> DownloadTask:
        out_dir = organized_dir(
            self.settings.download_dir, platform=info.platform, kind=entry.kind,
            by_platform=bool(self.settings.get("folder_by_platform")),
            by_type=bool(self.settings.get("folder_by_type")),
            by_date=bool(self.settings.get("folder_by_date")),
        )
        title = entry.title
        if info.is_gallery and (not title or title == info.title or title.startswith("Medya")):
            title = f"{info.title} - {entry.index:02d}"
        if disambiguate:
            # Aynı medyanın (entry) birden fazla formatı birlikte seçildiyse dosya adları
            # çarpışmasın diye ayırt edici bir ek eklenir (spec madde 4).
            hint = fmt.resolution or fmt.container.upper()
            title = f"{title} ({hint})"
        template = self.settings.get("naming_template")
        base = render_template(
            template, title=title, uploader=entry.uploader or info.uploader,
            platform=info.platform, media_id=entry.media_id, max_len=max_stem_length(out_dir),
        )
        convert = None
        if self.settings.get("advanced_convert_enabled") and fmt.kind == KIND_VIDEO:
            h = self.settings.get("advanced_convert_max_height")
            convert = ConvertSpec(self.settings.get("advanced_convert_codec"), self.settings.get("advanced_convert_container"),
                                  int(h) if h and h != "0" else None)
        return DownloadTask(
            title=title, url=entry.url or info.source_url, fmt=fmt, out_dir=out_dir, base_name=base,
            conflict=self.settings.get("conflict_behavior"), playlist_index=entry.playlist_index, platform=info.platform,
            rate_limit_bps=int(float(self.settings.get("speed_limit_mbps") or 0) * 1_000_000),
            max_retries=int(self.settings.get("retry_max_attempts")),
            backoff_start=int(self.settings.get("retry_backoff_seconds")),
            subtitle_langs=list(self.settings.get("subtitle_langs")), subtitle_format=self.settings.get("subtitle_format"),
            embed_subs=bool(self.settings.get("embed_subs")),
            embed_metadata=bool(self.settings.get("embed_metadata")), embed_thumbnail=bool(self.settings.get("embed_thumbnail")),
            proxy_url=self._resolved_proxy_url(), cookies_browser=self.settings.get("cookies_browser"), convert=convert,
        )

    def _download(self) -> None:
        info = self.info
        if not info:
            return
        pairs: list[tuple[MediaEntry, MediaFormat]] = []
        if info.is_gallery:
            for entry in self.gallery_table.checked_entries():
                fmt = self._pick_default(entry) or (entry.formats[0] if entry.formats else None)
                if fmt:
                    pairs.append((entry, fmt))
        else:
            entry = info.entries[0]
            for fmt in self.format_table.checked_formats():  # madde 4: birden fazla format birlikte
                pairs.append((entry, fmt))
        if not pairs:
            self._set_status("Önce en az bir seçenek işaretle.", error=True)
            return

        # Aynı medyanın (entry) birden fazla formatı seçildiyse dosya adları çarpışmasın
        # diye her birine ayırt edici bir ek eklenir (bkz. _make_task disambiguate).
        entry_counts: dict[int, int] = {}
        for entry, _fmt in pairs:
            entry_counts[id(entry)] = entry_counts.get(id(entry), 0) + 1

        # Duplicate detection (madde 20)
        dups = []
        for entry, _fmt in pairs:
            d = self.hist_service.check_duplicate(entry.url or info.source_url, entry.media_id)
            if d:
                dups.append(d)
        action = "redownload"
        if dups:
            action = ask_duplicate(self, dups)
            if action == "abort":
                return
            if action == "existing":
                for d in dups:
                    if d.file_exists:
                        reveal_in_folder(Path(d.record.file_path))
                self._set_status(f"{len(dups)} öğe zaten indirilmişti, mevcut dosyalar kullanıldı.")
                dup_urls = {d.record.url for d in dups}
                pairs = [(e, f) for e, f in pairs if (e.url or info.source_url) not in dup_urls]
                if not pairs:
                    return

        started = 0
        for entry, fmt in pairs:
            task = self._make_task(info, entry, fmt, disambiguate=entry_counts[id(entry)] > 1)
            if action == "copy":
                task.conflict = "new"
            elif action == "redownload":
                task.conflict = "overwrite" if any(d.record.url == task.url for d in dups) else task.conflict
            if self._start_download(info, entry, fmt, task):
                started += 1
        if started:
            self._set_status(
                f"{started} indirme başlatıldı."
                + (" (bazıları zaten kuyruktaydı, atlandı.)" if started < len(pairs) else "")
            )
            self.nav.select("downloads")
        elif pairs:
            self._set_status("Seçilenler zaten kuyrukta ya da indiriliyor.")

    def _active_duplicate(self, task: DownloadTask) -> bool:
        """Aynı (URL + format + hedef dosya) kombinasyonu zaten aktif kuyrukta mı? (spec madde
        5, 25 — aynı dosyanın iki kez / iki worker tarafından eklenmesini-indirilmesini engeller)."""
        target = task.out_dir / f"{task.base_name}.{task.fmt.container}"
        for i in range(self.dl_layout.count()):
            item = self.dl_layout.itemAt(i)
            w = item.widget() if item else None
            if not (isinstance(w, DownloadWidget) and w.is_active):
                continue
            existing_target = w.task.out_dir / f"{w.task.base_name}.{w.task.fmt.container}"
            if existing_target == target and w.task.url == task.url and w.task.fmt.format_id == task.fmt.format_id:
                return True
        return False

    def _start_download(
        self, info: MediaInfo, entry: MediaEntry, fmt: MediaFormat, task: Optional[DownloadTask] = None
    ) -> bool:
        task = task or self._make_task(info, entry, fmt)
        if self._active_duplicate(task):
            log.info("Aynı görev zaten aktif/kuyrukta, atlanıyor: %s", task.url)
            return False
        record_id = self.history.start(
            title=task.title, url=task.url, platform=info.platform, media_type=fmt.kind,
            file_path=str(task.out_dir / f"{task.base_name}.{fmt.container}"), file_name=f"{task.base_name}.{fmt.container}",
            resolution=fmt.resolution, thumbnail=info.thumbnail, duration=entry.duration,
            media_id=entry.media_id, format_container=fmt.container, downloaded_at=datetime.now(timezone.utc).isoformat(),
        )
        widget = DownloadWidget(task, self.manager, record_id)
        widget.remove_requested.connect(self._remove_download)
        widget.move_up_requested.connect(self._move_download_up)
        widget.move_down_requested.connect(self._move_download_down)
        widget.state_changed.connect(self._on_download_state_changed)
        self.dl_layout.insertWidget(0, widget)
        self._update_empty_downloads_label()
        widget.start(self.download_pool)
        self._reindex_priorities()
        self.nav.set_active_count(self._active_download_count())
        return True

    def _on_download_state_changed(self, widget: DownloadWidget) -> None:
        if widget.history_record_id is None:
            return
        if widget.state == "done" and widget._result:
            try:
                size = widget._result.stat().st_size
            except OSError:
                size = None
            fp = None
            try:
                from app.history.service import compute_fingerprint

                fp = compute_fingerprint(widget._result)
            except Exception:  # noqa: BLE001
                pass
            self.history.mark_status(widget.history_record_id, STATUS_COMPLETED, file_size=size,
                                     file_path=str(widget._result), fingerprint=fp)
            self._refresh_recent()
            action = self.settings.get("post_complete_action")
            if action == "notify":
                self.notifier.notify("İndirme tamamlandı", widget.name.text(),
                                     on_click=lambda p=widget._result: reveal_in_folder(p))
            elif action == "open_folder":
                reveal_in_folder(widget._result)
            elif action == "open_file":
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(widget._result)))
        elif widget.state == "failed":
            reason = widget.status.text()
            self.history.mark_status(widget.history_record_id, STATUS_FAILED, error_message=reason)
            self.notifier.notify("İndirme başarısız", widget.name.text(), ok=False)
        elif widget.state == "cancelled":
            self.history.mark_status(widget.history_record_id, STATUS_CANCELLED)
        self.nav.set_active_count(self._active_download_count())

    def _active_download_count(self) -> int:
        n = 0
        for i in range(self.dl_layout.count()):
            w = self.dl_layout.itemAt(i).widget()
            if isinstance(w, DownloadWidget) and w.is_active:
                n += 1
        return n

    def _update_empty_downloads_label(self) -> None:
        has_any = self.dl_layout.count() > 1  # +1 stretch
        self.empty_downloads_label.setVisible(not has_any)

    def _remove_download(self, widget: DownloadWidget) -> None:
        self.dl_layout.removeWidget(widget)
        widget.deleteLater()
        self._update_empty_downloads_label()
        self.nav.set_active_count(self._active_download_count())

    def _reindex_priorities(self) -> None:
        """Sıradaki (henüz başlamamış) indirmelerin gerçek başlama önceliğini görsel sıraya göre ayarlar."""
        widgets = [self.dl_layout.itemAt(i).widget() for i in range(self.dl_layout.count())]
        widgets = [w for w in widgets if isinstance(w, DownloadWidget)]
        n = len(widgets)
        for idx, w in enumerate(widgets):
            w.set_priority(n - idx)

    def _move_download_up(self, widget: DownloadWidget) -> None:
        idx = self.dl_layout.indexOf(widget)
        if idx > 0:
            self.dl_layout.removeWidget(widget)
            self.dl_layout.insertWidget(idx - 1, widget)
            self._reindex_priorities()

    def _move_download_down(self, widget: DownloadWidget) -> None:
        idx = self.dl_layout.indexOf(widget)
        if 0 <= idx < self.dl_layout.count() - 2:
            self.dl_layout.removeWidget(widget)
            self.dl_layout.insertWidget(idx + 1, widget)
            self._reindex_priorities()

    # ------------------------------------------------------------------ sistem tepsisi / kapanış
    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._closing = True
        from PySide6.QtWidgets import QApplication

        for i in range(self.dl_layout.count()):
            w = self.dl_layout.itemAt(i).widget()
            if isinstance(w, DownloadWidget) and w.is_active:
                w.worker.cancel()
        self.web_server.stop()
        QApplication.instance().quit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._closing:
            self._close_services()
            super().closeEvent(event)
            return
        active = self._active_download_count()
        if active and self.notifier.available and self.settings.get("close_to_tray"):
            choice = ask_close_with_active(self, active)
            if choice == "abort":
                event.ignore()
                return
            if choice == "cancel":
                for i in range(self.dl_layout.count()):
                    w = self.dl_layout.itemAt(i).widget()
                    if isinstance(w, DownloadWidget) and w.is_active:
                        w.worker.cancel()
                self._close_services()
                event.accept()
                return
            # arka planda devam et: pencereyi tepsiye gizle, indirmeleri KESME
            event.ignore()
            self.hide()
            self.notifier.notify("Arka planda çalışıyor", "İndirmeler devam ediyor.", force=True)
            return
        for i in range(self.dl_layout.count()):
            w = self.dl_layout.itemAt(i).widget()
            if isinstance(w, DownloadWidget) and w.is_active:
                w.worker.cancel()
        self._close_services()
        super().closeEvent(event)
