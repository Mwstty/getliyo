"""Ayarlar penceresi: Genel / İndirme / Dosyalar / Bildirimler / Görünüm / Gelişmiş / Gizlilik / Sistem."""
from __future__ import annotations

import shutil

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.history.db import HistoryDB
from app.media.ffmpeg_manager import FFmpegManager
from app.settings.defaults import (
    AUDIO_FORMAT_OPTIONS,
    CONCURRENCY_OPTIONS,
    CONFLICT_OPTIONS,
    COOKIE_BROWSER_OPTIONS,
    POST_COMPLETE_OPTIONS,
    PROXY_OPTIONS,
    QUALITY_OPTIONS,
    RETRY_BACKOFF_OPTIONS,
    SPEED_LIMIT_OPTIONS,
    THEME_OPTIONS,
    VIDEO_FORMAT_OPTIONS,
)
from app.settings.settings_manager import SettingsManager
from app.ui.workers import FunctionWorker
from app.utils.name_template import PRESET_TEMPLATES, validate_template
from app.utils.paths import settings_file
from app.utils.secret import protect
from app.utils.ytdlp_update import check_ytdlp


def _combo(options: list[tuple[str, str]], current: str) -> QComboBox:
    box = QComboBox()
    for key, label in options:
        box.addItem(label, key)
    box.setCurrentIndex(max(0, box.findData(current)))
    return box


class SettingsWindow(QDialog):
    def __init__(
        self,
        settings: SettingsManager,
        ffmpeg: FFmpegManager,
        history: HistoryDB | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ayarlar")
        self.setMinimumWidth(680)
        self.settings, self.ffmpeg, self.history = settings, ffmpeg, history
        self._workers: list[FunctionWorker] = []

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "Genel")
        tabs.addTab(self._build_download_tab(), "İndirme")
        tabs.addTab(self._build_files_tab(), "Dosyalar")
        tabs.addTab(self._build_network_tab(), "Ağ")
        tabs.addTab(self._build_web_tab(), "Web")
        tabs.addTab(self._build_notifications_tab(), "Bildirimler")
        tabs.addTab(self._build_appearance_tab(), "Görünüm")
        tabs.addTab(self._build_advanced_tab(), "Gelişmiş")
        tabs.addTab(self._build_privacy_tab(), "Gizlilik")
        tabs.addTab(self._build_system_tab(), "Sistem")

        save = QPushButton("KAYDET")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        cancel = QPushButton("Vazgeç")
        cancel.clicked.connect(self.reject)
        reset = QPushButton("Varsayılana Dön")
        reset.clicked.connect(self._reset_defaults)
        buttons = QHBoxLayout()
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addLayout(buttons)

    # ------------------------------------------------------------------ sekmeler
    def _build_general_tab(self) -> QWidget:
        self.dir_edit = QLineEdit(str(self.settings.download_dir))
        browse = QPushButton("Seç...")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.dir_edit, 1)
        row.addWidget(browse)
        self.quality = _combo(QUALITY_OPTIONS, self.settings.get("default_quality"))
        self.vformat = _combo(VIDEO_FORMAT_OPTIONS, self.settings.get("default_video_format"))
        self.aformat = _combo(AUDIO_FORMAT_OPTIONS, self.settings.get("default_audio_format"))
        general = QWidget()
        form = QFormLayout(general)
        form.addRow("İndirme klasörü", row)
        form.addRow("Varsayılan kalite (Hızlı İndir)", self.quality)
        form.addRow("Varsayılan video formatı", self.vformat)
        form.addRow("Varsayılan audio formatı", self.aformat)
        return general

    def _build_download_tab(self) -> QWidget:
        self.concurrency = _combo(CONCURRENCY_OPTIONS, self.settings.get("max_concurrent_downloads"))
        self.speed_limit = _combo(SPEED_LIMIT_OPTIONS, self.settings.get("speed_limit_mbps"))
        self.retry_backoff = _combo(RETRY_BACKOFF_OPTIONS, self.settings.get("retry_backoff_seconds"))
        self.retry_max = QSpinBox()
        self.retry_max.setRange(0, 20)
        self.retry_max.setValue(int(self.settings.get("retry_max_attempts")))
        w = QWidget()
        f = QFormLayout(w)
        f.addRow("Eşzamanlı indirme sayısı", self.concurrency)
        f.addRow("Hız limiti", self.speed_limit)
        f.addRow("Bağlantı koptuğunda tekrar deneme aralığı", self.retry_backoff)
        f.addRow("En fazla tekrar deneme", self.retry_max)
        return w

    def _build_files_tab(self) -> QWidget:
        self.conflict = _combo(CONFLICT_OPTIONS, self.settings.get("conflict_behavior"))
        self.naming = QComboBox()
        self.naming.setEditable(True)
        for tpl, label in PRESET_TEMPLATES:
            self.naming.addItem(f"{label}  ({tpl})", tpl)
        current_tpl = self.settings.get("naming_template")
        idx = self.naming.findData(current_tpl)
        if idx >= 0:
            self.naming.setCurrentIndex(idx)
        else:
            self.naming.setEditText(current_tpl)
        hint = QLabel("Kullanılabilir: {title} {uploader} {platform} {date} {id}")
        hint.setObjectName("muted")
        self.recycle_bin = QCheckBox("Silinen dosyaları Geri Dönüşüm Kutusu'na gönder")
        self.recycle_bin.setChecked(bool(self.settings.get("use_recycle_bin")))
        self.by_platform = QCheckBox("Platforma göre alt klasör aç (YouTube, X, ...)")
        self.by_platform.setChecked(bool(self.settings.get("folder_by_platform")))
        self.by_type = QCheckBox("Türe göre alt klasör aç (Video, Ses, Görsel)")
        self.by_type.setChecked(bool(self.settings.get("folder_by_type")))
        self.by_date = QCheckBox("Tarihe göre alt klasör aç")
        self.by_date.setChecked(bool(self.settings.get("folder_by_date")))
        self.embed_meta = QCheckBox("Başlık ve sanatçı bilgisini dosyaya göm")
        self.embed_meta.setChecked(bool(self.settings.get("embed_metadata")))
        self.embed_thumb = QCheckBox("Kapak görselini dosyaya göm")
        self.embed_thumb.setChecked(bool(self.settings.get("embed_thumbnail")))
        w = QWidget()
        f = QFormLayout(w)
        f.addRow("Aynı dosya varsa", self.conflict)
        f.addRow("Dosya adlandırma şablonu", self.naming)
        f.addRow("", hint)
        f.addRow(self.recycle_bin)
        f.addRow(self.by_platform)
        f.addRow(self.by_type)
        f.addRow(self.by_date)
        f.addRow(self.embed_meta)
        f.addRow(self.embed_thumb)
        return w

    def _build_web_tab(self) -> QWidget:
        self.web_autostart = QCheckBox("Uygulama açılınca web sunucuyu otomatik başlat")
        self.web_autostart.setChecked(bool(self.settings.get("web_server_autostart")))
        self.web_port = QSpinBox()
        self.web_port.setRange(1024, 65535)
        self.web_port.setValue(int(self.settings.get("web_server_port")))
        hint = QLabel(
            "Web sunucu, indirme sitesini yalnızca bu bilgisayarda (127.0.0.1) açar; ağdaki diğer cihazlar "
            "erişemez. Ana sayfadaki düğmeyle de başlatılıp durdurulabilir. Port değişikliği bir sonraki "
            "başlatmada geçerli olur. İnternete açmak için ayrı sunucu paketine (server/README.md) bak."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        w = QWidget()
        f = QFormLayout(w)
        f.addRow(self.web_autostart)
        f.addRow("Port", self.web_port)
        f.addRow("", hint)
        return w

    def _build_network_tab(self) -> QWidget:
        self.proxy_type = _combo(PROXY_OPTIONS, self.settings.get("proxy_type"))
        self.proxy_host = QLineEdit(self.settings.get("proxy_host"))
        self.proxy_port = QSpinBox()
        self.proxy_port.setRange(0, 65535)
        self.proxy_port.setValue(int(self.settings.get("proxy_port") or 0))
        self.proxy_user = QLineEdit(self.settings.get("proxy_user"))
        self.proxy_pass = QLineEdit()
        self.proxy_pass.setEchoMode(QLineEdit.Password)
        self.proxy_pass.setPlaceholderText("Değiştirmek için yaz, boş bırakırsan korunur")
        self.cookies = _combo(COOKIE_BROWSER_OPTIONS, self.settings.get("cookies_browser"))
        hint = QLabel("Çerezler, giriş gerektiren ya da yaş sınırlı içerikler için tarayıcından okunur.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        w = QWidget()
        f = QFormLayout(w)
        f.addRow("Proxy türü", self.proxy_type)
        f.addRow("Sunucu", self.proxy_host)
        f.addRow("Port", self.proxy_port)
        f.addRow("Kullanıcı adı", self.proxy_user)
        f.addRow("Parola", self.proxy_pass)
        f.addRow("Çerez kaynağı", self.cookies)
        f.addRow("", hint)
        return w

    def _build_notifications_tab(self) -> QWidget:
        self.notify_enabled = QCheckBox("Bildirimleri göster")
        self.notify_enabled.setChecked(bool(self.settings.get("notifications_enabled")))
        self.post_complete = _combo(POST_COMPLETE_OPTIONS, self.settings.get("post_complete_action"))
        w = QWidget()
        f = QFormLayout(w)
        f.addRow(self.notify_enabled)
        f.addRow("İndirme tamamlanınca", self.post_complete)
        return w

    def _build_appearance_tab(self) -> QWidget:
        self.theme = _combo(THEME_OPTIONS, self.settings.get("theme"))
        w = QWidget()
        f = QFormLayout(w)
        f.addRow("Tema", self.theme)
        return w

    def _build_advanced_tab(self) -> QWidget:
        self.clipboard_detect = QCheckBox("Panodan desteklenen bağlantıları algıla")
        self.clipboard_detect.setChecked(bool(self.settings.get("clipboard_detect_enabled")))
        self.clipboard_auto = QCheckBox("Algılanan bağlantıyı otomatik analiz et")
        self.clipboard_auto.setChecked(bool(self.settings.get("clipboard_auto_analyze")))
        self.close_to_tray = QCheckBox("Pencere kapatılınca sistem tepsisine küçült")
        self.close_to_tray.setChecked(bool(self.settings.get("close_to_tray")))
        self.start_tray = QCheckBox("Başlangıçta sistem tepsisinde başlat")
        self.start_tray.setChecked(bool(self.settings.get("start_minimized_to_tray")))
        self.convert_on = QCheckBox("İndirdikten sonra videoyu dönüştür (FFmpeg gerekir)")
        self.convert_on.setChecked(bool(self.settings.get("advanced_convert_enabled")))
        self.convert_codec = _combo([("h264", "H.264"), ("h265", "H.265"), ("vp9", "VP9"), ("av1", "AV1")],
                                    self.settings.get("advanced_convert_codec"))
        self.convert_container = _combo(VIDEO_FORMAT_OPTIONS, self.settings.get("advanced_convert_container"))
        self.convert_height = _combo(
            [("0", "Orijinal"), ("2160", "2160p"), ("1440", "1440p"), ("1080", "1080p"), ("720", "720p"), ("480", "480p")],
            self.settings.get("advanced_convert_max_height"),
        )
        w = QWidget()
        f = QFormLayout(w)
        f.addRow(self.clipboard_detect)
        f.addRow(self.clipboard_auto)
        f.addRow(self.close_to_tray)
        f.addRow(self.start_tray)
        f.addRow(self.convert_on)
        f.addRow("Dönüştürme codec'i", self.convert_codec)
        f.addRow("Dönüştürme kabı", self.convert_container)
        f.addRow("En yüksek çözünürlük", self.convert_height)
        return w

    def _build_privacy_tab(self) -> QWidget:
        text = QLabel(
            "getliyo herhangi bir kullanım verisi (telemetry) toplamaz veya "
            "dışarı göndermez. Geçmiş ve ayarlar yalnızca bu bilgisayarda, kendi "
            "klasöründe tutulur. Girdiğiniz bağlantılar, hata ayıklama loglarına "
            "gereksiz yere yazılmaz; şifre/çerez bilgisi hiçbir yere loglanmaz."
        )
        text.setWordWrap(True)
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(text)
        layout.addStretch(1)
        return w

    def _build_system_tab(self) -> QWidget:
        from yt_dlp.version import __version__ as ytdlp_version

        self.ytdlp_label = QLabel(ytdlp_version)
        self.ffmpeg_label = QLabel(self.ffmpeg.status_text())
        self.ffmpeg_label.setWordWrap(True)
        self.deno_label = QLabel("Hazır" if self.ffmpeg.deno_path else "Bulunamadı — YouTube'da bazı formatlar eksik olabilir")
        self.update_btn = QPushButton("yt-dlp güncellemesini kontrol et")
        self.update_btn.clicked.connect(self._check_updates)
        self.update_label = QLabel("")
        self.update_label.setWordWrap(True)
        self.ytdlp_auto = QCheckBox("Uygulama açılırken yt-dlp güncellemesini otomatik kontrol et")
        self.ytdlp_auto.setChecked(bool(self.settings.get("ytdlp_auto_check")))

        self.health_label = QLabel(self._health_check_text())
        self.health_label.setWordWrap(True)
        repair_btn = QPushButton("Sistem durumunu yenile")
        repair_btn.clicked.connect(lambda: self.health_label.setText(self._health_check_text()))

        w = QWidget()
        f = QFormLayout(w)
        f.addRow("Uygulama sürümü", QLabel("1.0.0"))
        f.addRow("yt-dlp sürümü", self.ytdlp_label)
        f.addRow("FFmpeg durumu", self.ffmpeg_label)
        f.addRow("JavaScript (Deno)", self.deno_label)
        f.addRow(self.update_btn, self.update_label)
        f.addRow("Sistem Durumu", self.health_label)
        f.addRow(self.ytdlp_auto)
        f.addRow(repair_btn)
        return w

    # ------------------------------------------------------------------ sistem durumu (madde 42)
    def _health_check_text(self) -> str:
        lines = []
        lines.append(("✓" if self.ffmpeg.is_available else "⚠") + " FFmpeg")
        lines.append(("✓" if self.ffmpeg.ffprobe_path else "⚠") + " FFprobe")
        lines.append("✓ yt-dlp")
        try:
            if self.history:
                self.history.count()
            db_ok = True
        except Exception:
            db_ok = False
        lines.append(("✓" if db_ok else "⚠") + " Veritabanı (Geçmiş)")
        out_dir = self.settings.download_dir
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            writable = True
        except OSError:
            writable = False
        lines.append(("✓" if writable else "⚠") + " İndirme klasörü (yazılabilir)")
        try:
            free = shutil.disk_usage(out_dir if writable else ".").free
            disk_ok = free > 500 * 1024 * 1024
        except OSError:
            disk_ok, free = False, 0
        lines.append(("✓" if disk_ok else "⚠") + f" Disk alanı ({free // (1024**3)} GB boş)")
        lines.append(("✓" if settings_file().parent.exists() else "⚠") + " Yapılandırma")
        return "\n".join(lines)

    # ------------------------------------------------------------------ eylemler
    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "İndirme klasörü", self.dir_edit.text())
        if chosen:
            self.dir_edit.setText(chosen)

    def _save(self) -> None:
        template = self.naming.currentData() or self.naming.currentText()
        if not validate_template(template):
            QMessageBox.warning(
                self, "Geçersiz şablon",
                "Dosya adlandırma şablonunda bilinmeyen bir {token} var. "
                "Kullanılabilir tokenlar: {title} {uploader} {platform} {date} {id}",
            )
            return
        self.settings.update(
            {
                "download_dir": self.dir_edit.text().strip(),
                "default_quality": self.quality.currentData(),
                "default_video_format": self.vformat.currentData(),
                "default_audio_format": self.aformat.currentData(),
                "conflict_behavior": self.conflict.currentData(),
                "naming_template": template,
                "max_concurrent_downloads": self.concurrency.currentData(),
                "speed_limit_mbps": self.speed_limit.currentData(),
                "retry_backoff_seconds": self.retry_backoff.currentData(),
                "use_recycle_bin": self.recycle_bin.isChecked(),
                "notifications_enabled": self.notify_enabled.isChecked(),
                "post_complete_action": self.post_complete.currentData(),
                "theme": self.theme.currentData(),
                "clipboard_detect_enabled": self.clipboard_detect.isChecked(),
                "clipboard_auto_analyze": self.clipboard_auto.isChecked(),
                "close_to_tray": self.close_to_tray.isChecked(),
                "start_minimized_to_tray": self.start_tray.isChecked(),
                "retry_max_attempts": self.retry_max.value(),
                "folder_by_platform": self.by_platform.isChecked(),
                "folder_by_type": self.by_type.isChecked(),
                "folder_by_date": self.by_date.isChecked(),
                "embed_metadata": self.embed_meta.isChecked(),
                "embed_thumbnail": self.embed_thumb.isChecked(),
                "proxy_type": self.proxy_type.currentData(),
                "proxy_host": self.proxy_host.text().strip(),
                "proxy_port": self.proxy_port.value(),
                "proxy_user": self.proxy_user.text().strip(),
                "cookies_browser": self.cookies.currentData(),
                "advanced_convert_enabled": self.convert_on.isChecked(),
                "advanced_convert_codec": self.convert_codec.currentData(),
                "advanced_convert_container": self.convert_container.currentData(),
                "advanced_convert_max_height": self.convert_height.currentData(),
                "ytdlp_auto_check": self.ytdlp_auto.isChecked(),
                "web_server_autostart": self.web_autostart.isChecked(),
                "web_server_port": self.web_port.value(),
            }
        )
        if self.proxy_pass.text():
            self.settings.set("proxy_password_enc", protect(self.proxy_pass.text()))
        self.accept()

    def _reset_defaults(self) -> None:
        """Spec madde 69: varsayılana dön ama history/indirilen dosyalar SİLİNMEZ (zaten
        bu pencere onlara dokunmuyor, sadece settings.json sıfırlanır)."""
        if QMessageBox.question(
            self, "Varsayılana dön",
            "Tüm ayarlar varsayılana dönecek (geçmişiniz ve indirdiğiniz dosyalar "
            "ETKİLENMEYECEK). Devam edilsin mi?",
        ) != QMessageBox.Yes:
            return
        from app.settings.defaults import BUILTIN_DEFAULTS

        self.settings.update(dict(BUILTIN_DEFAULTS))
        self.accept()

    def _check_updates(self) -> None:
        self.update_btn.setEnabled(False)
        self.update_label.setText("Kontrol ediliyor...")
        worker = FunctionWorker(check_ytdlp)
        worker.signals.result.connect(self._on_versions)
        worker.signals.error.connect(lambda m: self.update_label.setText(m))
        worker.signals.finished.connect(lambda: self.update_btn.setEnabled(True))
        self._workers.append(worker)
        QThreadPool.globalInstance().start(worker)

    def _on_versions(self, status) -> None:
        if status.latest is None:
            self.update_label.setText("Sürüm bilgisi alınamadı (internet?).")
        elif status.newer:
            self.update_label.setText(
                f"Yeni yt-dlp var: {status.latest}. Siteler sık değiştiği için uygulamayı güncel yt-dlp ile "
                "yeniden derle (scripts\\build.bat her seferinde günceller)."
            )
        else:
            self.update_label.setText("yt-dlp güncel.")
