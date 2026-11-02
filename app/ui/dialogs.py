"""Küçük diyaloglar: toplu URL, istatistik, kapanış onayı, mükerrer içerik."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from app.history.service import DuplicateInfo
from app.media.media_utils import format_size
from app.utils.url_extract import parse_urls

MAX_TEXT_FILE = 1_000_000


def read_urls_from_file(path: str) -> list[str]:
    """Bir metin dosyasındaki URL'leri okur (en fazla 1 MB, UTF-8/varsayılan)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_TEXT_FILE)
    except OSError:
        return []
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return parse_urls(raw.decode(enc))
        except UnicodeDecodeError:
            continue
    return []


class BatchUrlDialog(QDialog):
    """Satır satır URL listesi / metin dosyası → kuyruğa ekle."""

    def __init__(self, parent: QWidget | None = None, initial: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Toplu URL")
        self.setMinimumSize(560, 420)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("Her satıra bir bağlantı yapıştır...")
        self.edit.setPlainText(initial)
        self.count = QLabel("")
        self.count.setObjectName("muted")
        self.edit.textChanged.connect(self._update_count)
        load = QPushButton("Metin dosyasından yükle...")
        load.clicked.connect(self._load_file)
        ok = QPushButton("KUYRUĞA EKLE")
        ok.setObjectName("primary")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Vazgeç")
        cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(load)
        row.addStretch(1)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay = QVBoxLayout(self)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.count)
        lay.addLayout(row)
        self.urls: list[str] = []
        self._update_count()

    def _update_count(self) -> None:
        self.count.setText(f"{len(parse_urls(self.edit.toPlainText()))} geçerli bağlantı bulundu")

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Metin dosyası seç", "", "Metin (*.txt *.csv *.list);;Tümü (*.*)")
        if path:
            found = read_urls_from_file(path)
            existing = self.edit.toPlainText().rstrip()
            self.edit.setPlainText((existing + "\n" if existing else "") + "\n".join(found))

    def _accept(self) -> None:
        self.urls = parse_urls(self.edit.toPlainText())
        if not self.urls:
            QMessageBox.information(self, "Toplu URL", "Geçerli bir bağlantı bulunamadı.")
            return
        self.accept()


class StatsDialog(QDialog):
    def __init__(self, stats: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("İstatistikler")
        by_type = stats.get("by_type", {})
        lines = [
            f"Toplam dosya: {stats.get('total_files', 0)}",
            f"Toplam indirilen: {format_size(stats.get('total_bytes', 0))}",
            f"Video: {by_type.get('video', {}).get('count', 0)}   Görsel: {by_type.get('image', {}).get('count', 0)}   "
            f"Ses: {by_type.get('audio', {}).get('count', 0)}",
            "", "Platform dağılımı:",
        ]
        lines += [f"  {name}: {n}" for name, n in stats.get("by_platform", {}).items()] or ["  —"]
        lab = QLabel("\n".join(lines))
        ok = QPushButton("Kapat"); ok.clicked.connect(self.accept)
        lay = QVBoxLayout(self); lay.addWidget(lab); lay.addWidget(ok)


def ask_close_with_active(parent: QWidget, active: int) -> str:
    """'background' | 'cancel' | 'abort' (spec madde 28)."""
    box = QMessageBox(parent)
    box.setWindowTitle("İndirmeler devam ediyor")
    box.setText(f"{active} indirme devam ediyor.")
    bg = box.addButton("Arka planda devam et", QMessageBox.AcceptRole)
    cancel = box.addButton("İndirmeleri iptal et", QMessageBox.DestructiveRole)
    box.addButton("Vazgeç", QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    return "background" if clicked is bg else "cancel" if clicked is cancel else "abort"


def ask_duplicate(parent: QWidget, dups: list[DuplicateInfo]) -> str:
    """'existing' | 'redownload' | 'copy' | 'abort' (spec madde 20)."""
    first = dups[0]
    box = QMessageBox(parent)
    box.setWindowTitle("Bu içerik daha önce indirilmiş")
    text = "Bu içerik daha önce indirilmiş."
    if len(dups) > 1:
        text += f"\n({len(dups)} öğe daha önce indirilmiş görünüyor.)"
    text += f"\n\n{first.record.title}"
    if not first.file_exists:
        text += "\n(Dosya artık kayıtlı konumda bulunamadı.)"
    box.setText(text)
    existing = box.addButton("Mevcut dosyayı kullan", QMessageBox.AcceptRole)
    re = box.addButton("Yeniden indir", QMessageBox.DestructiveRole)
    copy = box.addButton("Yeni kopya oluştur", QMessageBox.ActionRole)
    box.addButton("Vazgeç", QMessageBox.RejectRole)
    if not first.file_exists:
        existing.setEnabled(False)
    box.exec()
    c = box.clickedButton()
    return "existing" if c is existing else "redownload" if c is re else "copy" if c is copy else "abort"
