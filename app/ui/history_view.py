"""Geçmiş / Favoriler ekranı: arama, filtreler, dosya işlemleri, toplu silme (spec 15-20, 45-47, 52, 71)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.history.db import HistoryDB
from app.history.models import HistoryRecord
from app.history.service import HistoryService
from app.media.media_utils import format_duration, format_size, kind_label
from app.ui.download_widget import reveal_in_folder

PAGE_SIZE = 100
DATE_OPTIONS = [("", "Tümü"), ("1", "Bugün"), ("7", "7 gün"), ("30", "30 gün")]
MEDIA_OPTIONS = [("", "Tümü"), ("video", "Video"), ("image", "Image"), ("audio", "Audio")]


def _open_file(path: Path) -> None:
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "", str(path)], shell=False)  # noqa: S603,S607
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class HistoryView(QWidget):
    redownload_requested = Signal(str)  # url

    def __init__(self, db: HistoryDB, service: HistoryService, settings, favorites_only: bool = False) -> None:
        super().__init__()
        self.db, self.service, self.settings = db, service, settings
        self.favorites_only = favorites_only
        self._offset = 0
        self._total = 0

        title = QLabel("FAVORİLER" if favorites_only else "GEÇMİŞ")
        title.setObjectName("section")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Başlık veya bağlantıda ara...")
        self.search.textChanged.connect(self._reload_debounced)
        self.platform_combo = QComboBox()
        self.platform_combo.addItem("Tümü", "")
        self.platform_combo.currentIndexChanged.connect(self.reload)
        self.media_combo = QComboBox()
        for k, l in MEDIA_OPTIONS:
            self.media_combo.addItem(l, k)
        self.media_combo.currentIndexChanged.connect(self.reload)
        self.date_combo = QComboBox()
        for k, l in DATE_OPTIONS:
            self.date_combo.addItem(l, k)
        self.date_combo.currentIndexChanged.connect(self.reload)
        filters = QHBoxLayout()
        for w in (self.search, self.platform_combo, self.media_combo, self.date_combo):
            filters.addWidget(w, 1 if w is self.search else 0)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["", "Başlık", "Platform", "Tür", "Süre", "Boyut", "Tarih"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.itemChanged.connect(self._on_check_changed)
        self.table.itemDoubleClicked.connect(lambda it: self._open_selected_file() if it.column() > 0 else None)

        self.select_all_cb = QCheckBox("Tümünü seç")
        self.select_all_cb.toggled.connect(self._select_all)
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        self.load_more_btn = QPushButton("Daha fazla yükle")
        self.load_more_btn.clicked.connect(self._load_more)
        self.load_more_btn.hide()

        del_hist_btn = QPushButton("SEÇİLENLERİ GEÇMİŞTEN SİL")
        del_hist_btn.clicked.connect(self._delete_selected_from_history)
        del_files_btn = QPushButton("SEÇİLEN DOSYALARI SİL")
        del_files_btn.setObjectName("danger")
        del_files_btn.clicked.connect(self._delete_selected_files)
        clear_hist_btn = QPushButton("TÜM GEÇMİŞİ TEMİZLE")
        clear_hist_btn.clicked.connect(self._clear_history)
        clear_all_btn = QPushButton("TÜM GEÇMİŞİ VE DOSYALARI TEMİZLE")
        clear_all_btn.setObjectName("danger")
        clear_all_btn.clicked.connect(self._clear_history_and_files)

        top = QHBoxLayout()
        top.addWidget(title, 1)
        top.addWidget(self.count_label)
        bulk = QHBoxLayout()
        bulk.addWidget(self.select_all_cb)
        bulk.addStretch(1)
        for b in (del_hist_btn, del_files_btn):
            bulk.addWidget(b)
        danger = QHBoxLayout()
        danger.addStretch(1)
        danger.addWidget(clear_hist_btn)
        danger.addWidget(clear_all_btn)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(filters)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.load_more_btn)
        lay.addLayout(bulk)
        lay.addLayout(danger)
        self._rows: list[HistoryRecord] = []

    # ------------------------------------------------------------------ veri
    def _filters(self) -> dict:
        since = ""
        days = self.date_combo.currentData()
        if days:
            from datetime import datetime, timedelta, timezone

            since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
        return dict(
            search=self.search.text().strip(),
            platform=self.platform_combo.currentData() or "",
            media_type=self.media_combo.currentData() or "",
            since_iso=since,
            favorites_only=self.favorites_only,
            statuses=("completed",),
        )

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
        self._offset = 0
        self._refresh_platform_list()
        self._rows = self.db.list(**self._filters(), limit=PAGE_SIZE, offset=0)
        self._total = self.db.count(**self._filters())
        self._render(reset=True)

    def _reload_debounced(self) -> None:
        self.reload()  # arama kutusu için basit; büyük geçmişte de tek sorgu ucuzdur

    def _load_more(self) -> None:
        self._offset += PAGE_SIZE
        self._rows += self.db.list(**self._filters(), limit=PAGE_SIZE, offset=self._offset)
        self._render(reset=False)

    def _refresh_platform_list(self) -> None:
        current = self.platform_combo.currentData()
        self.platform_combo.blockSignals(True)
        self.platform_combo.clear()
        self.platform_combo.addItem("Tümü", "")
        for p in self.db.platforms():
            self.platform_combo.addItem(p, p)
        idx = self.platform_combo.findData(current)
        self.platform_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.platform_combo.blockSignals(False)

    def _render(self, reset: bool) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._rows))
        for r, rec in enumerate(self._rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Unchecked)
            check.setData(Qt.UserRole, rec.id)
            self.table.setItem(r, 0, check)
            title = rec.title + ("  ★" if rec.is_favorite else "")
            missing = self.service.file_status_text(rec)
            if missing:
                title += f"   ⚠ {missing}"
            self.table.setItem(r, 1, QTableWidgetItem(title))
            self.table.setItem(r, 2, QTableWidgetItem(rec.platform or "—"))
            self.table.setItem(r, 3, QTableWidgetItem(kind_label(rec.media_type)))
            self.table.setItem(r, 4, QTableWidgetItem(format_duration(rec.duration)))
            self.table.setItem(r, 5, QTableWidgetItem(format_size(rec.file_size)))
            self.table.setItem(r, 6, QTableWidgetItem((rec.downloaded_at or "")[:16].replace("T", " ")))
        self.table.blockSignals(False)
        self.count_label.setText(f"{len(self._rows)} / {self._total}")
        self.load_more_btn.setVisible(len(self._rows) < self._total)
        self.select_all_cb.blockSignals(True)
        self.select_all_cb.setChecked(False)
        self.select_all_cb.blockSignals(False)

    def _on_check_changed(self, item) -> None:
        pass  # checkbox durumu doğrudan tabloda tutuluyor, ayrı state gerekmiyor

    def _select_all(self, checked: bool) -> None:
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)

    def _checked_ids(self) -> list[int]:
        return [
            self.table.item(r, 0).data(Qt.UserRole)
            for r in range(self.table.rowCount())
            if self.table.item(r, 0).checkState() == Qt.Checked
        ]

    def _record_at(self, row: int) -> Optional[HistoryRecord]:
        rid = self.table.item(row, 0).data(Qt.UserRole)
        return next((r for r in self._rows if r.id == rid), None)

    # ------------------------------------------------------------------ tekil eylemler (madde 16, 46)
    def _context_menu(self, pos) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        rec = self._record_at(row)
        if not rec:
            return
        menu = QMenu(self)
        menu.addAction("Dosyayı Aç", lambda: self._open_file(rec))
        menu.addAction("Klasörde Göster", lambda: self._reveal(rec))
        menu.addAction("URL'yi Kopyala", lambda: QGuiApplication.clipboard().setText(rec.url))
        menu.addAction("Başlığı Kopyala", lambda: QGuiApplication.clipboard().setText(rec.title))
        menu.addAction("Tekrar İndir", lambda: self.redownload_requested.emit(rec.url))
        menu.addAction(("Favoriden Çıkar" if rec.is_favorite else "Favoriye Ekle"), lambda: self._toggle_favorite(rec))
        menu.addSeparator()
        if self.service.file_status_text(rec):
            menu.addAction("Dosyayı Bul...", lambda: self._find_file(rec))
        menu.addAction("Geçmişten Kaldır", lambda: self._delete_from_history([rec.id]))
        menu.addAction("Dosyayı Sil", lambda: self._delete_file([rec.id]))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_selected_file(self) -> None:
        row = self.table.currentRow()
        rec = self._record_at(row) if row >= 0 else None
        if rec:
            self._open_file(rec)

    def _open_file(self, rec: HistoryRecord) -> None:
        p = Path(rec.file_path) if rec.file_path else None
        if p and p.is_file():
            _open_file(p)
        else:
            QMessageBox.information(self, "Dosya bulunamadı", "Dosya bulunamadı ya da taşınmış.")

    def _reveal(self, rec: HistoryRecord) -> None:
        p = Path(rec.file_path) if rec.file_path else None
        if p and p.exists():
            reveal_in_folder(p)
        else:
            QMessageBox.information(self, "Dosya bulunamadı", "Dosya bulunamadı ya da taşınmış.")

    def _toggle_favorite(self, rec: HistoryRecord) -> None:
        self.db.set_favorite(rec.id, not rec.is_favorite)
        self.reload()

    def _find_file(self, rec: HistoryRecord) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Dosyayı bul")
        if path and self.service.relink(rec.id, Path(path)):
            self.reload()

    # ------------------------------------------------------------------ toplu eylemler (madde 16, 17)
    def _delete_from_history(self, ids: list[int]) -> None:
        if not ids:
            return
        self.service.delete_from_history(ids)
        self.reload()

    def _delete_selected_from_history(self) -> None:
        ids = self._checked_ids()
        if not ids:
            return
        if QMessageBox.question(self, "Geçmişten sil", f"{len(ids)} kayıt geçmişten silinsin mi? "
                                "(Dosyalar bilgisayarınızda kalır.)") == QMessageBox.Yes:
            self._delete_from_history(ids)

    def _delete_file(self, ids: list[int]) -> None:
        if QMessageBox.question(self, "Dosyayı sil", f"{len(ids)} dosya "
                                f"{'Geri Dönüşüm Kutusu’na gönderilsin' if self.settings.get('use_recycle_bin') else 'KALICI olarak silinsin'} mi?"
                                ) != QMessageBox.Yes:
            return
        res = self.service.delete_files_bulk(ids, bool(self.settings.get("use_recycle_bin")))
        self.reload()
        if res.skipped:
            QMessageBox.warning(self, "Bazı dosyalar silinemedi",
                                "\n".join(f"{title if (title:=self._title_of(rid)) else rid}: {why}" for rid, why in res.skipped[:10]))

    def _title_of(self, rid: int) -> str:
        rec = self.db.get(rid)
        return rec.title if rec else ""

    def _delete_selected_files(self) -> None:
        ids = self._checked_ids()
        if ids:
            self._delete_file(ids)

    def _clear_history(self) -> None:
        if QMessageBox.question(self, "Tüm geçmişi temizle",
                                "Tüm geçmiş silinecek. Dosyalarınız bilgisayarınızda KALACAK. Devam edilsin mi?"
                                ) == QMessageBox.Yes:
            self.service.clear_history()
            self.reload()

    def _clear_history_and_files(self) -> None:
        """İki aşamalı onay — çok güçlü bir işlem (spec madde 17)."""
        if QMessageBox.warning(self, "TÜM geçmişi ve dosyaları sil",
                               "Bu, uygulamanın indirdiği TÜM dosyaları ve geçmişi siler. "
                               "Bu işlem GERİ ALINAMAZ (Geri Dönüşüm Kutusu ayarı kapalıysa).",
                               QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
            return
        if QMessageBox.warning(self, "Emin misin?",
                               "Bunu gerçekten yapmak istediğinden emin misin? Uygulamanın yönetmediği "
                               "hiçbir dosyaya dokunulmaz, ama kendi indirdiklerinizin TAMAMI silinecek.",
                               QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
            return
        res = self.service.clear_history_and_files(bool(self.settings.get("use_recycle_bin")))
        self.reload()
        QMessageBox.information(self, "Tamamlandı", f"{res.deleted} dosya silindi." +
                                (f" {len(res.skipped)} dosya atlandı." if res.skipped else ""))
