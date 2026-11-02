"""Hata Merkezi (spec madde 40): hangi URL, ne zaman, neden başarısız oldu; tekrar dene."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.history.db import HistoryDB


class ErrorCenterView(QWidget):
    retry_requested = Signal(str)  # url

    def __init__(self, db: HistoryDB) -> None:
        super().__init__()
        self.db = db
        title = QLabel("HATA MERKEZİ")
        title.setObjectName("section")
        self.info = QLabel("Başarısız/iptal edilen indirmeler burada listelenir.")
        self.info.setObjectName("muted")
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Başlık / URL", "Sebep", "Zaman", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        clear_btn = QPushButton("Hata kayıtlarını temizle")
        clear_btn.clicked.connect(self._clear)
        top = QHBoxLayout()
        top.addWidget(title, 1)
        top.addWidget(clear_btn)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.info)
        lay.addWidget(self.table, 1)
        self._rows = []

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
        self._rows = self.db.list(statuses=("failed", "cancelled"), limit=200)
        self.table.setRowCount(len(self._rows))
        for r, rec in enumerate(self._rows):
            self.table.setItem(r, 0, QTableWidgetItem(rec.title or rec.url))
            reason = rec.error_message or ("Kullanıcı tarafından iptal edildi" if rec.status == "cancelled" else "Bilinmeyen hata")
            self.table.setItem(r, 1, QTableWidgetItem(reason))
            self.table.setItem(r, 2, QTableWidgetItem((rec.downloaded_at or "")[:16].replace("T", " ")))
            btn = QPushButton("TEKRAR DENE")
            btn.clicked.connect(lambda _=False, u=rec.url: self.retry_requested.emit(u))
            self.table.setCellWidget(r, 3, btn)
        self.info.setText(f"{len(self._rows)} başarısız/iptal edilmiş indirme.")

    def _clear(self) -> None:
        if QMessageBox.question(self, "Temizle", "Hata kayıtları geçmişten silinsin mi? (Dosyalara dokunulmaz.)") == QMessageBox.Yes:
            self.db.clear_errors()
            self.reload()
