"""Tek örnek (single-instance) desteği: QLocalServer/QLocalSocket ile.

Uygulama zaten açıksa yeni çağrı (ör. tarayıcı eklentisinden) URL'yi mevcut pencereye
iletir ve kendisi hemen kapanır; böylece aynı anda iki pencere açılmaz.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "getliyoTekOrnek"
CONNECT_TIMEOUT_MS = 300


def forward_to_running_instance(url: str) -> bool:
    """Zaten çalışan bir örnek varsa URL'yi ona iletir. Başarılıysa True döner."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    socket.write(url.encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
    socket.disconnectFromServer()
    return True


class SingleInstanceServer:
    """Bu örneğin sunucusu: sonradan gelen URL'leri dinler."""

    def __init__(self, on_url: Callable[[str], None]) -> None:
        self._on_url = on_url
        self._sockets: list[QLocalSocket] = []
        QLocalServer.removeServer(SERVER_NAME)  # önceki çökmeden kalan kilidi temizle
        self.server = QLocalServer()
        self.server.newConnection.connect(self._accept)
        self.server.listen(SERVER_NAME)

    def _accept(self) -> None:
        socket = self.server.nextPendingConnection()
        if not socket:
            return
        self._sockets.append(socket)

        def on_ready() -> None:
            data = bytes(socket.readAll())
            if data:
                self._on_url(data.decode("utf-8", errors="ignore"))
            socket.disconnectFromServer()
            if socket in self._sockets:
                self._sockets.remove(socket)

        socket.readyRead.connect(on_ready)
