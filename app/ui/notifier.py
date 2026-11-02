"""Windows bildirimleri ve sistem tepsisi (QSystemTrayIcon — ek bağımlılık gerekmez)."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from app.settings.settings_manager import SettingsManager


class Notifier:
    def __init__(self, settings: SettingsManager, icon: QIcon, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self.settings = settings
        self.tray: Optional[QSystemTrayIcon] = None
        self._click_action: Optional[Callable[[], None]] = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon)
            self.tray.setToolTip("getliyo")
            menu = QMenu()
            menu.addAction("Aç", on_show)
            menu.addSeparator()
            menu.addAction("Çıkış", on_quit)
            self._menu = menu
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: on_show() if reason == QSystemTrayIcon.Trigger else None)
            self.tray.messageClicked.connect(self._on_message_clicked)

    @property
    def available(self) -> bool:
        return self.tray is not None

    def show_tray(self) -> None:
        if self.tray:
            self.tray.show()

    def notify(self, title: str, message: str, *, ok: bool = True, on_click: Optional[Callable[[], None]] = None,
               force: bool = False) -> bool:
        """Bildirimi ayar açıksa gösterir. Gösterildiyse True döner."""
        if not (force or self.settings.get("notifications_enabled")) or not self.tray:
            return False
        self._click_action = on_click
        self.tray.show()
        self.tray.showMessage(title, message, QSystemTrayIcon.Information if ok else QSystemTrayIcon.Warning, 6000)
        return True

    def _on_message_clicked(self) -> None:
        if self._click_action:
            self._click_action()
