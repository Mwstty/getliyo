"""Tema sistemi: Koyu / Açık / Sistem (QSS).

Renk paleti, UI redesign spesifikasyonunun (bkz. proje dokümanları) BİREBİR verdiği hex
değerlerdir — rastgele farklı mavi/yeşil/kırmızı tonları KULLANILMAZ, her yerde bu tokenlar
üzerinden tutarlı renk uygulanır.
"""
from __future__ import annotations

DARK: dict[str, str] = {
    "BG": "#0F1115",
    "PANEL": "#151922",       # secondary background
    "CARD": "#1B202B",        # card / panel
    "HOVER": "#232A36",
    "BORDER": "#2A3140",
    "TEXT": "#F5F7FA",        # primary text
    "MUTED": "#9CA4B3",       # secondary text
    "DISABLED": "#5B6370",
    "ACCENT": "#4F8CFF",
    "ACCENT_HOVER": "#6A9DFF",
    "ACCENT_PRESSED": "#3D73D9",
    "OK": "#3CCB7F",          # success
    "WARNING": "#F5B942",
    "ERR": "#FF5C67",         # error
    "ON_ACCENT": "#FFFFFF",
}
# Türetilmiş tokenlar (temel paletten tutarlı şekilde hesaplanır)
DARK.update({
    "PANEL_ALT": DARK["CARD"],
    "ROW_ALT": DARK["PANEL"],
    "SEL": "rgba(79, 140, 255, 0.16)",
    "DISABLED_BORDER": DARK["BORDER"],
    "PRIMARY_DIS_BG": "#2A3140",
    "PRIMARY_DIS_FG": DARK["DISABLED"],
    "OK_BG": "rgba(60, 203, 127, 0.16)",
    "WARNING_BG": "rgba(245, 185, 66, 0.16)",
    "ERR_BG": "rgba(255, 92, 103, 0.16)",
    "ACCENT_BG": "rgba(79, 140, 255, 0.16)",
})

LIGHT: dict[str, str] = {
    "BG": "#F5F7FA",
    "PANEL": "#EEF1F6",
    "CARD": "#FFFFFF",
    "HOVER": "#E7ECF3",
    "BORDER": "#D7DEE8",
    "TEXT": "#10151C",
    "MUTED": "#5B6370",
    "DISABLED": "#AEB4BD",
    "ACCENT": "#2F6FED",
    "ACCENT_HOVER": "#4F8CFF",
    "ACCENT_PRESSED": "#1F57C7",
    "OK": "#1F9D5C",
    "WARNING": "#C98A1D",
    "ERR": "#D83A46",
    "ON_ACCENT": "#FFFFFF",
}
LIGHT.update({
    "PANEL_ALT": LIGHT["CARD"],
    "ROW_ALT": LIGHT["PANEL"],
    "SEL": "rgba(47, 111, 237, 0.12)",
    "DISABLED_BORDER": LIGHT["BORDER"],
    "PRIMARY_DIS_BG": "#D7DEE8",
    "PRIMARY_DIS_FG": LIGHT["DISABLED"],
    "OK_BG": "rgba(31, 157, 92, 0.12)",
    "WARNING_BG": "rgba(201, 138, 29, 0.12)",
    "ERR_BG": "rgba(216, 58, 70, 0.12)",
    "ACCENT_BG": "rgba(47, 111, 237, 0.12)",
})

# Geriye dönük uyumluluk: eski kod bu sabitleri doğrudan import edebilir (koyu tema
# değerleridir). YENİ kod bunun yerine current_colors() kullanmalı -- aksi halde tema Light'a
# alındığında bu sabitler yanlış (koyu) renk döndürür.
BG, PANEL, PANEL_ALT, BORDER = DARK["BG"], DARK["PANEL"], DARK["PANEL_ALT"], DARK["BORDER"]
TEXT, MUTED, ACCENT, ACCENT_HOVER = DARK["TEXT"], DARK["MUTED"], DARK["ACCENT"], DARK["ACCENT_HOVER"]
OK, ERR, WARNING = DARK["OK"], DARK["ERR"], DARK["WARNING"]

_FONT = '"Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'

_TEMPLATE = """
* { font-family: """ + _FONT + """; font-size: 13px; color: @TEXT@; }
QToolTip { background: @CARD@; color: @TEXT@; border: 1px solid @BORDER@; padding: 4px 8px; border-radius: 6px; }
QMainWindow, QDialog, QWidget#root { background: @BG@; }
QLabel#title { font-size: 22px; font-weight: 600; }
QLabel#hero { font-size: 26px; font-weight: 600; }
QLabel#subtitle { color: @MUTED@; font-size: 12px; }
QLabel#section { color: @MUTED@; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#status { color: @MUTED@; }
QLabel#status[error="true"] { color: @ERR@; }
QLabel#muted { color: @MUTED@; }
QLabel#empty { color: @MUTED@; font-size: 13px; }
QFrame#card, QFrame#download { background: @CARD@; border: 1px solid @BORDER@; border-radius: 8px; }
QFrame#card:hover, QFrame#download:hover { border-color: @HOVER@; }
QFrame#nav { background: @PANEL@; border-right: 1px solid @BORDER@; }
QPushButton#navbtn { text-align: left; padding: 10px 16px; border: none; border-radius: 0; background: transparent; font-weight: 500; color: @MUTED@; }
QPushButton#navbtn:hover { background: @HOVER@; color: @TEXT@; }
QPushButton#navbtn:checked { background: @HOVER@; color: @TEXT@; border-left: 3px solid @ACCENT@; font-weight: 600; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; }
QLabel#thumb { background: @PANEL@; border-radius: 6px; color: @MUTED@; }
QLineEdit, QComboBox, QSpinBox { background: @CARD@; border: 1px solid @BORDER@; border-radius: 6px; padding: 8px 12px; selection-background-color: @ACCENT@; }
QLineEdit#url { font-size: 14px; padding: 13px 14px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid @ACCENT@; }
QComboBox QAbstractItemView { background: @CARD@; border: 1px solid @BORDER@; selection-background-color: @SEL@; selection-color: @TEXT@; }
QPlainTextEdit { background: @CARD@; border: 1px solid @BORDER@; border-radius: 6px; padding: 8px; }
QPushButton { background: @CARD@; border: 1px solid @BORDER@; border-radius: 6px; padding: 8px 14px; font-weight: 500; }
QPushButton:hover { background: @HOVER@; border-color: @HOVER@; }
QPushButton:pressed { background: @HOVER@; }
QPushButton:disabled { color: @DISABLED@; border-color: @DISABLED_BORDER@; }
QPushButton#primary { background: @ACCENT@; border: none; color: @ON_ACCENT@; font-weight: 600; padding: 13px 22px; }
QPushButton#primary:hover { background: @ACCENT_HOVER@; }
QPushButton#primary:pressed { background: @ACCENT_PRESSED@; }
QPushButton#primary:disabled { background: @PRIMARY_DIS_BG@; color: @PRIMARY_DIS_FG@; }
QPushButton#ghost { background: transparent; border: none; color: @MUTED@; }
QPushButton#ghost:hover { background: @HOVER@; color: @TEXT@; }
QPushButton#danger { color: @ERR@; }
QPushButton#danger:hover { border-color: @ERR@; }
QPushButton#recent { text-align: left; padding: 10px 14px; border-radius: 8px; font-weight: 400; }
QPushButton#chip { padding: 6px 12px; border-radius: 14px; font-size: 12px; }
QPushButton#iconbtn { padding: 6px; border-radius: 6px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; }
QTableWidget { background: @CARD@; border: 1px solid @BORDER@; border-radius: 8px; gridline-color: transparent; alternate-background-color: @ROW_ALT@; selection-background-color: @SEL@; selection-color: @TEXT@; }
QHeaderView::section { background: @PANEL@; color: @MUTED@; border: none; padding: 8px; font-weight: 600; }
QProgressBar { background: @PANEL@; border: none; border-radius: 3px; height: 6px; text-align: center; color: transparent; }
QProgressBar::chunk { background: @ACCENT@; border-radius: 3px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: @BORDER@; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @MUTED@; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QTabWidget::pane { border: 1px solid @BORDER@; border-radius: 8px; background: @CARD@; }
QTabBar::tab { background: transparent; color: @MUTED@; padding: 8px 14px; }
QTabBar::tab:selected { color: @TEXT@; border-bottom: 2px solid @ACCENT@; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid @BORDER@; border-radius: 4px; background: @CARD@; }
QCheckBox::indicator:hover { border-color: @ACCENT@; }
QCheckBox::indicator:checked { background: @ACCENT@; border-color: @ACCENT@; }
QMenu { background: @CARD@; border: 1px solid @BORDER@; padding: 4px; border-radius: 8px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: @SEL@; }
QLabel#badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
QLabel#badge[state="running"] { background: @ACCENT_BG@; color: @ACCENT@; }
QLabel#badge[state="done"] { background: @OK_BG@; color: @OK@; }
QLabel#badge[state="failed"] { background: @ERR_BG@; color: @ERR@; }
QLabel#badge[state="paused"] { background: @WARNING_BG@; color: @WARNING@; }
QLabel#badge[state="queued"] { background: @PANEL@; color: @MUTED@; }
"""


def build_stylesheet(palette: dict[str, str]) -> str:
    css = _TEMPLATE
    for key, value in palette.items():
        css = css.replace(f"@{key}@", value)
    return css


STYLESHEET = build_stylesheet(DARK)

_current_palette: dict[str, str] = DARK


def current_colors() -> dict[str, str]:
    """En son apply_theme() ile uygulanan paletin bir kopyasını döndürür. download_widget.py
    gibi tüketiciler, statik (koyu temaya sabit) renk sabitleri import etmek yerine rengi
    GÖSTERİLECEĞİ anda buradan okumalı -- aksi halde Light temaya geçince renkler yanlış kalır."""
    return dict(_current_palette)


def resolve_theme(setting: str) -> str:
    """'dark' | 'light' | 'system' -> 'dark' | 'light' (sistem: Qt renk şemasına bakar)."""
    if setting in ("dark", "light"):
        return setting
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGuiApplication

        scheme = QGuiApplication.styleHints().colorScheme()
        return "light" if scheme == Qt.ColorScheme.Light else "dark"
    except Exception:  # noqa: BLE001
        return "dark"


def apply_theme(app, setting: str) -> str:
    global _current_palette
    name = resolve_theme(setting)
    _current_palette = LIGHT if name == "light" else DARK
    app.setStyleSheet(build_stylesheet(_current_palette))
    return name
