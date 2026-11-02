"""Arka plan işleri: arayüzün donmaması için her şey QThreadPool'da çalışır."""
from __future__ import annotations

import time
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from app.downloaders.base_downloader import DownloadControl, DownloadTask, ProgressInfo
from app.downloaders.manager import DownloaderManager
from app.utils.errors import CancelledError, SkippedError, friendly_message
from app.utils.logger import get_logger

log = get_logger("worker")


class FunctionSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class FunctionWorker(QRunnable):
    """Herhangi bir fonksiyonu arka planda çalıştırır."""

    def __init__(self, fn: Callable[..., Any], *args: Any) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.fn, self.args = fn, args
        self.signals = FunctionSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.fn(*self.args))
        except Exception as exc:  # noqa: BLE001
            log.exception("Arka plan işi başarısız")
            self.signals.error.emit(friendly_message(exc))
        finally:
            self.signals.finished.emit()


class DownloadSignals(QObject):
    started = Signal()  # havuz işi gerçekten çalıştırmaya başladı (ilk progress'ten önce) -> "Hazırlanıyor"
    progress = Signal(object)
    finished = Signal(str)
    skipped = Signal(str)
    cancelled = Signal()
    paused = Signal()  # gerçek iptalden farklı: dosya korunuyor, devam ettirilebilir
    failed = Signal(str)


class DownloadWorker(QRunnable):
    """Bir DownloadTask'ı çalıştırır. DURAKLATMA/DEVAM: pause() çağrıldığında iş .part
    dosyasını silmeden durur; aynı task ile YENİ bir DownloadWorker oluşturup tekrar
    başlatmak (resume) kaldığı yerden devam eder (yt-dlp continuedl / Range header)."""

    def __init__(self, manager: DownloaderManager, task: DownloadTask) -> None:
        super().__init__()
        self.setAutoDelete(False)
        self.manager, self.task = manager, task
        self.control = DownloadControl()
        self.signals = DownloadSignals()
        self._last = 0.0

    # Geriye dönük uyumluluk: eski kod `worker.cancel_event.set()` çağırıyordu.
    @property
    def cancel_event(self):  # noqa: ANN201
        return self.control.stop_event

    def cancel(self) -> None:
        """Gerçek iptal: tamamlanan yarım dosya silinir."""
        self.control.stop(keep_partial=False)

    def pause(self) -> None:
        """Duraklat: yarım dosya KORUNUR, sonra aynı task ile devam ettirilebilir."""
        self.control.stop(keep_partial=True)

    def _emit_progress(self, info: ProgressInfo) -> None:
        now = time.monotonic()
        if info.status == "İndiriliyor" and now - self._last < 0.1:
            return
        self._last = now
        self.signals.progress.emit(info)

    def run(self) -> None:
        if self.control.is_set():
            (self.signals.paused if self.control.keep_partial else self.signals.cancelled).emit()
            return
        self.signals.started.emit()  # havuz gerçekten çalıştırmaya başladı -> "Hazırlanıyor"
        try:
            path = self.manager.download(self.task, self._emit_progress, self.control)
            self.signals.finished.emit(str(path))
        except CancelledError:
            (self.signals.paused if self.control.keep_partial else self.signals.cancelled).emit()
        except SkippedError as exc:
            self.signals.skipped.emit(exc.path)
        except Exception as exc:  # noqa: BLE001
            log.exception("İndirme başarısız: %s", self.task.url)
            self.signals.failed.emit(friendly_message(exc))
