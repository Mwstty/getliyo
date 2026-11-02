"""Sol gezinme çubuğu: ANA SAYFA / İNDİRMELER / GEÇMİŞ / FAVORİLER / HATALAR / AYARLAR."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QLabel, QPushButton, QVBoxLayout

PAGES = [
    ("home", "ANA SAYFA"),
    ("downloads", "İNDİRMELER"),
    ("history", "GEÇMİŞ"),
    ("favorites", "FAVORİLER"),
    ("errors", "HATA MERKEZİ"),
]


class NavRail(QFrame):
    page_selected = Signal(str)
    settings_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("nav")
        self.setFixedWidth(190)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 16, 0, 12)
        lay.setSpacing(0)
        brand = QLabel("getliyo")
        brand.setObjectName("title")
        brand.setContentsMargins(18, 0, 0, 14)
        lay.addWidget(brand)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: dict[str, QPushButton] = {}
        for key, label in PAGES:
            b = QPushButton(label)
            b.setObjectName("navbtn")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.select(k))
            self.group.addButton(b)
            self.buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)
        self.badge = QLabel("")
        self.badge.setObjectName("muted")
        self.badge.setContentsMargins(18, 0, 0, 6)
        lay.addWidget(self.badge)
        settings = QPushButton("AYARLAR")
        settings.setObjectName("navbtn")
        settings.clicked.connect(self.settings_requested.emit)
        lay.addWidget(settings)
        self.buttons["home"].setChecked(True)

    def select(self, key: str) -> None:
        self.buttons[key].setChecked(True)
        self.page_selected.emit(key)

    def set_active_count(self, n: int) -> None:
        self.buttons["downloads"].setText(f"İNDİRMELER ({n})" if n else "İNDİRMELER")
