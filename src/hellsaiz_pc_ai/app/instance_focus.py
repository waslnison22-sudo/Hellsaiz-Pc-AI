"""Focus the already running instance instead of a dead-end message box.

The desktop app keeps a file lock (`single_instance.SingleInstanceLock`) to stay
single. That lock says "already running" but cannot raise the existing window,
so a second launch ended in a dialog. This helper adds a tiny local socket: the
primary instance listens, a secondary launch asks for "raise" and exits.
"""

from __future__ import annotations

import logging
import os
import sys

SOCKET_BASE = "HellsaizPC_AI.raise"
RAISE = b"raise"


def socket_name() -> str:
    user = os.environ.get("USERNAME") or "user"
    return f"{SOCKET_BASE}.{user.casefold()}"


def _qt_network():
    try:
        from PySide6.QtNetwork import QLocalServer, QLocalSocket

        return QLocalServer, QLocalSocket
    except ImportError:  # pragma: no cover - headless runners
        return None, None


def ask_to_raise(timeout_ms: int = 700) -> bool:
    """Tell the running instance to come forward; False when nobody listens."""
    _server, socket_cls = _qt_network()
    if socket_cls is None or sys.platform not in {"win32"} and not sys.platform.startswith("linux"):
        return False
    socket = socket_cls()
    socket.connectToServer(socket_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    socket.write(RAISE)
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class RaiseServer:
    """Listens for 'raise' requests and calls the window callback."""

    def __init__(self, on_raise) -> None:
        self._on_raise = on_raise
        self._server = None

    def start(self) -> bool:
        server_cls, _socket = _qt_network()
        if server_cls is None:
            return False
        server = server_cls()
        server.setSocketOptions(server_cls.SocketOption.UserAccessOption)
        if not server.listen(socket_name()):
            server_cls.removeServer(socket_name())
            if not server.listen(socket_name()):
                logging.warning("Raise server is unavailable; second launches stay silent")
                return False
        server.newConnection.connect(self._accept)
        self._server = server
        return True

    def _accept(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue
            payload = bytes(connection.readAll())
            connection.disconnectFromServer()
            connection.deleteLater()
            if payload.startswith(RAISE):
                try:
                    self._on_raise()
                except Exception:  # noqa: BLE001 - raising is best effort
                    logging.debug("Raise callback failed", exc_info=True)
