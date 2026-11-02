"""Format tablosu (tek medya) ve galeri tablosu (birden fazla medya, onay kutulu)."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from app.downloaders.base_downloader import MediaEntry, MediaFormat
from app.media.media_utils import format_size, kind_label


def _item(text: str, right: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setTextAlignment((Qt.AlignRight if right else Qt.AlignLeft) | Qt.AlignVCenter)
    return it


def _setup(table: QTableWidget, headers: list[str]) -> None:
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.verticalHeader().setDefaultSectionSize(32)


class FormatTable(QTableWidget):
    """☑ | Tür | Çözünürlük | FPS | Codec | Boyut | Format

    Onay kutulu çoklu seçim: kullanıcı birden fazla formatı (ör. hem video hem ses)
    aynı anda işaretleyip hepsini birlikte indirebilir (spec madde 3/4)."""

    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        _setup(self, ["", "Tür", "Çözünürlük", "FPS", "Codec", "Boyut", "Format"])
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._formats: list[MediaFormat] = []
        self.itemChanged.connect(lambda _i: self.selection_changed.emit())

    def set_formats(self, formats: list[MediaFormat]) -> None:
        self.blockSignals(True)
        self._formats = list(formats)
        self.setRowCount(len(formats))
        for r, f in enumerate(formats):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Unchecked)
            self.setItem(r, 0, check)
            fps = f"{f.fps:g}" if f.fps else "—"
            cells = [
                (kind_label(f.kind), False),
                (f.resolution or "—", True),
                (fps, True),
                (f.codec or "—", False),
                (format_size(f.filesize, f.size_estimated), True),
                (f.container.upper(), False),
            ]
            for c, (text, right) in enumerate(cells):
                self.setItem(r, c + 1, _item(text, right))
        self.blockSignals(False)
        self.selection_changed.emit()

    def _find_row(self, fmt: MediaFormat) -> Optional[int]:
        for r, f in enumerate(self._formats):
            if f is fmt or (f.format_id == fmt.format_id and f.kind == fmt.kind and f.container == fmt.container):
                return r
        for r, f in enumerate(self._formats):  # container değişmiş olabilir (preset override)
            if f.format_id == fmt.format_id:
                return r
        return None

    def preselect(self, fmt: Optional[MediaFormat], exclusive: bool = True) -> None:
        """Varsayılan formatı işaretler. exclusive=True ise diğer satırların işaretini kaldırır.
        fmt'nin container'ı (örn. preset'ten gelen "best_mp4" override) satırın saklı format
        nesnesine ve Format sütunundaki görünür metne de yansıtılır."""
        if fmt is None:
            return
        row = self._find_row(fmt)
        if row is None:
            return
        self.blockSignals(True)
        if exclusive:
            for r in range(self.rowCount()):
                if r != row:
                    self.item(r, 0).setCheckState(Qt.Unchecked)
        self._formats[row] = fmt
        self.item(row, 6).setText(fmt.container.upper())
        self.item(row, 0).setCheckState(Qt.Checked)
        self.blockSignals(False)
        self.selection_changed.emit()

    def set_all(self, checked: bool) -> None:
        self.blockSignals(True)
        for r in range(self.rowCount()):
            self.item(r, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.blockSignals(False)
        self.selection_changed.emit()

    def checked_formats(self) -> list[MediaFormat]:
        return [f for r, f in enumerate(self._formats) if self.item(r, 0).checkState() == Qt.Checked]


class GalleryTable(QTableWidget):
    """☑ | Ad | Tür | Çözünürlük | Boyut | Format"""

    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        _setup(self, ["", "Ad", "Tür", "Çözünürlük", "Boyut", "Format"])
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._entries: list[MediaEntry] = []
        self.itemChanged.connect(lambda _i: self.selection_changed.emit())

    def set_entries(
        self,
        entries: list[MediaEntry],
        pick: Callable[[MediaEntry], Optional[MediaFormat]],
        preselect_index: Optional[int] = None,
    ) -> None:
        """preselect_index verilirse (ör. X'in /photo/2 deep-link'i) SADECE o öğe işaretli
        gelir, diğerleri kullanıcı isterse seçsin diye görünür ama boş kalır."""
        self.blockSignals(True)
        self._entries = list(entries)
        self.setRowCount(len(entries))
        counters: dict[str, int] = {}
        names = {"image": "Fotoğraf", "video": "Video", "audio": "Ses"}
        for r, e in enumerate(entries):
            counters[e.kind] = counters.get(e.kind, 0) + 1
            fmt = pick(e)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            checked = (r + 1 == preselect_index) if preselect_index else True
            check.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.setItem(r, 0, check)
            label = f"{names.get(e.kind, 'Medya')} {counters[e.kind]}"
            shown = label if e.title.startswith(("http", "Medya")) or not e.title else f"{label} — {e.title}"
            self.setItem(r, 1, _item(shown))
            self.setItem(r, 2, _item(kind_label(e.kind)))
            self.setItem(r, 3, _item((fmt.resolution if fmt else "") or "—", True))
            self.setItem(r, 4, _item(format_size(fmt.filesize, fmt.size_estimated) if fmt else "—", True))
            self.setItem(r, 5, _item(fmt.container.upper() if fmt else "—"))
        self.blockSignals(False)
        self.selection_changed.emit()

    def set_all(self, checked: bool) -> None:
        self.blockSignals(True)
        for r in range(self.rowCount()):
            self.item(r, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.blockSignals(False)
        self.selection_changed.emit()

    def checked_entries(self) -> list[MediaEntry]:
        return [e for r, e in enumerate(self._entries) if self.item(r, 0).checkState() == Qt.Checked]
