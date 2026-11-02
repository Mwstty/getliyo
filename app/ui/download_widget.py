"""Tek bir indirmenin satırı: yüzde, MB/GB, hız, ETA, dosya adı, durum,
iptal/duraklat/devam/tekrar dene/öncelik değiştir — hepsi gerçek işlev görür."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from app.downloaders.base_downloader import DownloadTask, ProgressInfo
from app.downloaders.manager import DownloaderManager
from app.media.media_utils import format_eta, format_size, format_speed
from app.ui.styles import current_colors
from app.ui.workers import DownloadWorker

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_PAUSED = "paused"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_CANCELLED = "cancelled"


def reveal_in_folder(path: Path) -> None:
    if sys.platform == "win32" and path.exists():
        subprocess.Popen(["explorer", "/select,", str(path)])  # noqa: S603,S607 - argüman listesi, shell yok
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


class DownloadWidget(QFrame):
    remove_requested = Signal(object)
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)
    # (widget, history_record_id | None, final_path | None, status) -> history kaydını günceller
    state_changed = Signal(object)

    def __init__(self, task: DownloadTask, manager: DownloaderManager, history_record_id: Optional[int] = None) -> None:
        super().__init__()
        self.setObjectName("download")
        self.task = task
        self.manager = manager
        self.worker = DownloadWorker(manager, task)
        self._pool: QThreadPool | None = None
        self._result: Path | None = None
        self._finished = False
        self.state = STATE_QUEUED
        self.history_record_id = history_record_id
        self._retry_count = 0

        self.name = QLabel(f"{task.base_name}.{task.fmt.container}")
        self.name.setObjectName("cardTitle")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.percent = QLabel("0%")
        self.detail = QLabel("")
        self.detail.setObjectName("muted")
        self.status = QLabel("Sırada...")

        self.up_btn = QPushButton("YUKARI")
        self.up_btn.setToolTip("Sırada yukarı taşı (henüz başlamamışsa önceliğini artırır)")
        self.up_btn.clicked.connect(lambda: self.move_up_requested.emit(self))
        self.down_btn = QPushButton("AŞAĞI")
        self.down_btn.setToolTip("Sırada aşağı taşı")
        self.down_btn.clicked.connect(lambda: self.move_down_requested.emit(self))

        self.pause_btn = QPushButton("DURAKLAT")
        self.pause_btn.clicked.connect(self.pause)
        self.resume_btn = QPushButton("DEVAM ET")
        self.resume_btn.clicked.connect(self.resume)
        self.resume_btn.hide()
        self.retry_btn = QPushButton("TEKRAR DENE")
        self.retry_btn.clicked.connect(self.resume)  # aynı task, aynı dosya -> retry de kaldığı yerden dener
        self.retry_btn.hide()
        self.cancel_btn = QPushButton("İPTAL")
        self.cancel_btn.clicked.connect(self.cancel)
        self.show_btn = QPushButton("KLASÖRDE GÖSTER")
        self.show_btn.clicked.connect(lambda: self._result and reveal_in_folder(self._result))
        self.show_btn.hide()
        self.remove_btn = QPushButton("KALDIR")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        self.remove_btn.hide()

        top = QHBoxLayout()
        top.addWidget(self.up_btn)
        top.addWidget(self.down_btn)
        top.addWidget(self.name, 1)
        top.addWidget(self.percent)
        mid = QHBoxLayout()
        mid.addWidget(self.status, 1)
        for b in (self.show_btn, self.retry_btn, self.resume_btn, self.pause_btn, self.remove_btn, self.cancel_btn):
            mid.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addWidget(self.bar)
        lay.addWidget(self.detail)
        lay.addLayout(mid)

        self._connect_signals()

    def _connect_signals(self) -> None:
        s = self.worker.signals
        s.started.connect(self._on_started)
        s.progress.connect(self._on_progress)
        s.finished.connect(self._on_finished)
        s.skipped.connect(self._on_skipped)
        s.cancelled.connect(self._on_cancelled)
        s.paused.connect(self._on_paused)
        s.failed.connect(self._on_failed)

    def start(self, pool: QThreadPool, priority: int = 0) -> None:
        self._pool = pool
        self.state = STATE_RUNNING
        pool.start(self.worker, priority)

    @property
    def is_active(self) -> bool:
        return not self._finished

    _started_running = False

    def _on_started(self) -> None:
        """Havuz işi gerçekten çalıştırmaya başladı ama ilk progress event'i henüz gelmedi —
        kullanıcıya "Sırada..." yerine "Hazırlanıyor" göstererek UI'nin donmadığını belli eder."""
        if self._finished:
            return
        self.status.setText("Hazırlanıyor...")

    def _on_progress(self, p: ProgressInfo) -> None:
        self._started_running = True
        if self._finished:
            return
        self.status.setText(p.status or "İndiriliyor")
        if p.filename:
            self.name.setText(p.filename.replace(".part", ""))
        if p.indeterminate or p.percent is None:
            self.bar.setRange(0, 0)
            self.percent.setText("")
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(p.percent * 10))
            self.percent.setText(f"{p.percent:.1f}%")
        parts = []
        if p.total_bytes:
            parts.append(f"{format_size(p.done_bytes)} / {format_size(p.total_bytes)}")
        elif p.done_bytes:
            parts.append(format_size(p.done_bytes))
        if p.speed:
            parts.append(format_speed(p.speed))
        if p.eta is not None:
            parts.append(f"Kalan: {format_eta(p.eta)}")
        self.detail.setText("   •   ".join(parts))

    # ------------------------------------------------------------ eylemler
    def set_priority(self, priority: int) -> bool:
        """Hâlâ kuyruktaysa (başlamadıysa) önceliğini değiştirir — sıradaki konumunu
        gerçekten etkiler (Qt'nin QThreadPool önceliklendirmesi). Zaten çalışıyorsa
        sessizce başarısız olur (no-op), bu normaldir."""
        if not self._pool or self._finished:
            return False
        if self._pool.tryTake(self.worker):
            self._pool.start(self.worker, priority)
            return True
        return False

    def pause(self) -> None:
        """Gerçek duraklatma: indirilen kısım silinmez, DEVAM ET ile kaldığı yerden sürer."""
        self.pause_btn.setEnabled(False)
        if self._pool and self._pool.tryTake(self.worker):
            # Kuyrukta bekliyordu, hiç başlamamıştı -> doğrudan duraklatılmış say
            self._on_paused()
            return
        self.status.setText("Duraklatılıyor...")
        self.worker.pause()

    def resume(self) -> None:
        """Aynı task ile YENİ bir worker oluşturup tekrar başlatır (kaldığı yerden devam)."""
        if not self._pool:
            return
        self._retry_count += 1
        self._finished = False
        self.state = STATE_RUNNING
        self._started_running = False
        self.worker = DownloadWorker(self.manager, self.task)
        self._connect_signals()
        self.resume_btn.hide()
        self.retry_btn.hide()
        self.remove_btn.hide()
        self.cancel_btn.show()
        self.pause_btn.show()
        self.pause_btn.setEnabled(True)
        self.status.setStyleSheet("")
        self.status.setText("Devam ediliyor...")
        self.bar.setRange(0, 0)
        self.percent.setText("")
        self.state_changed.emit(self)
        self._pool.start(self.worker)

    def cancel(self) -> None:
        """Gerçek iptal: yarım dosya silinir, bu görev bir daha devam ettirilemez."""
        self.cancel_btn.setEnabled(False)
        self.status.setText("İptal ediliyor...")
        self.worker.cancel()
        if self._pool and self._pool.tryTake(self.worker):  # henüz başlamadıysa kuyruktan çıkar
            self._on_cancelled()

    # ---- sinyal yuvaları
    def _finish_ui(self, text: str, color: str | None = None, state: str = STATE_DONE) -> None:
        self._finished = True
        self.state = state
        self.up_btn.hide()
        self.down_btn.hide()
        self.cancel_btn.hide()
        self.pause_btn.hide()
        self.resume_btn.hide()
        self.retry_btn.hide()
        self.remove_btn.show()
        self.bar.setRange(0, 1000)
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};" if color else "")

    def _on_finished(self, path: str) -> None:
        self._result = Path(path)
        self.name.setText(self._result.name)
        self.bar.setValue(1000)
        self.percent.setText("100%")
        self.detail.setText("")
        self._finish_ui("Tamamlandı", current_colors()["OK"], STATE_DONE)
        self.show_btn.show()
        self.state_changed.emit(self)

    def _on_skipped(self, path: str) -> None:
        self._result = Path(path)
        self._finish_ui("Atlandı — aynı dosya zaten var", None, STATE_DONE)
        self.show_btn.show()
        self.state_changed.emit(self)

    def _on_cancelled(self) -> None:
        self.bar.setValue(0)
        self.percent.setText("")
        self._finish_ui("İptal edildi", None, STATE_CANCELLED)
        self.state_changed.emit(self)

    def _on_paused(self) -> None:
        self.state = STATE_PAUSED
        self.up_btn.hide()
        self.down_btn.hide()
        self.cancel_btn.hide()
        self.pause_btn.hide()
        self.retry_btn.hide()
        self.resume_btn.show()
        self.remove_btn.show()
        self.status.setText("Duraklatıldı")
        self.status.setStyleSheet("")

    def _on_failed(self, message: str) -> None:
        self.bar.setValue(0)
        self.percent.setText("")
        self.detail.setText("")
        self._finish_ui(message, current_colors()["ERR"], STATE_FAILED)
        self.retry_btn.show()  # basarisiz indirmede TEKRAR DENE gercekten task'i yeniden calistirir
        self.state_changed.emit(self)
