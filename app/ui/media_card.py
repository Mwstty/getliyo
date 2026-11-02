"""Analiz sonrası medya kartı: küçük resim, başlık, platform, tür, süre, çözünürlük, boyut."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from app.downloaders.base_downloader import MediaInfo
from app.media.media_utils import best_resolution_text, format_duration, format_size, kind_label


class MediaCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self.thumb = QLabel("Önizleme yok")
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(224, 126)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.title = QLabel()
        self.title.setObjectName("cardTitle")
        self.title.setWordWrap(True)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(4)
        self._values: dict[str, QLabel] = {}
        for i, name in enumerate(["Kaynak", "Tür", "Süre", "Çözünürlük", "Dosya boyutu", "Öğe sayısı"]):
            head = QLabel(name.upper())
            head.setObjectName("section")
            val = QLabel("—")
            self._values[name] = val
            self.grid.addWidget(head, (i // 3) * 2, i % 3)
            self.grid.addWidget(val, (i // 3) * 2 + 1, i % 3)
        right = QVBoxLayout()
        right.addWidget(self.title)
        right.addLayout(self.grid)
        right.addStretch(1)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(16)
        lay.addWidget(self.thumb, 0, Qt.AlignTop)
        lay.addLayout(right, 1)

    def set_info(self, info: MediaInfo) -> None:
        self.title.setText(info.title)
        first = info.entries[0]
        best = first.formats[0] if first.formats else None
        size = next((f for f in first.formats if f.filesize), None)
        self._values["Kaynak"].setText(info.platform or "—")
        kinds = {e.kind for e in info.entries}
        self._values["Tür"].setText(" + ".join(kind_label(k) for k in sorted(kinds)))
        self._values["Süre"].setText(format_duration(info.duration))
        self._values["Çözünürlük"].setText(best_resolution_text(first))
        self._values["Dosya boyutu"].setText(format_size(size.filesize, size.size_estimated) if size and not info.is_gallery else "—")
        self._values["Öğe sayısı"].setText(str(len(info.entries)))
        pix = QPixmap()
        if info.thumbnail_bytes and pix.loadFromData(info.thumbnail_bytes):
            self.thumb.setPixmap(pix.scaled(self.thumb.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.thumb.setText("")
        else:
            self.thumb.setPixmap(QPixmap())
            self.thumb.setText("Önizleme yok")
        del best
