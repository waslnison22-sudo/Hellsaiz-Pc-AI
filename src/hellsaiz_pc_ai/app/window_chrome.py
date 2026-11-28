"""Frameless window chrome: our own title bar, drag, and window buttons."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QPainterPath, QPalette, QRegion
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizeGrip,
    QWidget,
)


class WindowTitleBar(QWidget):
    """Drag area with custom minimise / maximise / close buttons."""

    def __init__(self, window: QMainWindow) -> None:
        super().__init__(window)
        self._window = window
        self._drag_origin: QPoint | None = None
        self.setObjectName("windowTitleBar")
        self.setFixedHeight(36)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0B0B0B"))
        self.setPalette(palette)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        # Style locally: the title bar is a menu widget and must not depend on
        # the page stylesheet cascading into it.
        self.setStyleSheet(
            """
            QWidget#windowTitleBar { background: #0B0B0B; }
            QLabel#windowTitleBarLabel {
                color: #6F6B66;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1px;
            }
            QPushButton#windowMinButton, QPushButton#windowMaxButton {
                background: transparent;
                border: 0;
                color: #A6A29C;
                font-size: 17px;
                font-weight: 700;
                padding: 0;
                min-height: 0;
                min-width: 0;
            }
            QPushButton#windowMinButton:hover, QPushButton#windowMaxButton:hover {
                background: #1F1F1D;
                border-radius: 6px;
                color: #F2EFEA;
            }
            QPushButton#windowCloseButton {
                background: transparent;
                border: 0;
                color: #A6A29C;
                font-size: 15px;
                font-weight: 700;
                padding: 0;
                min-height: 0;
                min-width: 0;
            }
            QPushButton#windowCloseButton:hover {
                background: #C0392B;
                border-radius: 6px;
                color: #FFFFFF;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(8)

        self._title = QLabel(window.windowTitle(), self)
        self._title.setObjectName("windowTitleBarLabel")
        layout.addWidget(self._title)
        layout.addStretch(1)

        self._minimize = self._button("windowMinButton", "\u2013", "Свернуть")
        self._minimize.clicked.connect(self._window.showMinimized)
        layout.addWidget(self._minimize)

        self._maximize = self._button("windowMaxButton", "\u25a1", "Развернуть")
        self._maximize.clicked.connect(self.toggle_maximized)
        layout.addWidget(self._maximize)

        self._close = self._button("windowCloseButton", "\u2715", "Закрыть")
        self._close.setObjectName("windowCloseButton")
        self._close.clicked.connect(self._window.close)
        layout.addWidget(self._close)

    def _button(self, name: str, text: str, tooltip: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setObjectName(name)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(40, 30)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
            self._maximize.setText("\u25a1")
            self._maximize.setToolTip("Развернуть")
        else:
            self._window.showMaximized()
            self._maximize.setText("\u2750")
            self._maximize.setToolTip("Восстановить")

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
            self._drag_origin = event.globalPosition().toPoint() - self._window.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximized()
        super().mouseDoubleClickEvent(event)

    def sync_title(self) -> None:
        self._title.setText(self._window.windowTitle())


class _EdgeGrip(QWidget):
    """A thin strip on one window edge that starts a system resize."""

    def __init__(self, window: QMainWindow, edges: Qt.Edge, cursor) -> None:
        super().__init__(window)
        self._window = window
        self._edges = edges
        self.setObjectName("windowEdgeResizer")
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        window.installEventFilter(self)

    def relayout(self) -> None:
        width, height = self._window.width(), self._window.height()
        thickness = 6
        if self._edges == Qt.Edge.LeftEdge:
            self.setGeometry(0, thickness, thickness, max(1, height - thickness * 2))
        elif self._edges == Qt.Edge.RightEdge:
            self.setGeometry(width - thickness, thickness, thickness, max(1, height - thickness * 2))
        elif self._edges == Qt.Edge.TopEdge:
            self.setGeometry(0, 0, width, thickness)
        else:
            self.setGeometry(0, height - thickness, width, thickness)
        self.raise_()

    def eventFilter(self, watched, event):  # noqa: N802 - Qt naming
        if watched is self._window and event.type() == QEvent.Type.Resize:
            self.relayout()
        return False

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemResize(self._edges)
                event.accept()
                return
        super().mousePressEvent(event)


def _install_edges(window: QMainWindow) -> list[_EdgeGrip]:
    grips = [
        _EdgeGrip(window, Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor),
        _EdgeGrip(window, Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor),
        _EdgeGrip(window, Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor),
        _EdgeGrip(window, Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor),
    ]
    for grip in grips:
        grip.relayout()
        grip.show()
    return grips


class _RoundedMask:
    """Keeps the frameless window corners rounded like the top bar."""

    RADIUS = 18

    def __init__(self, window: QMainWindow) -> None:
        self._window = window
        window.installEventFilter(self)
        self._apply()

    def _apply(self) -> None:
        window = self._window
        if window is None or window.width() <= 0:
            return
        path = QPainterPath()
        path.addRoundedRect(0, 0, window.width(), window.height(), self.RADIUS, self.RADIUS)
        window.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def eventFilter(self, watched, event):  # noqa: N802 - Qt naming
        if watched is self._window and event.type() == QEvent.Type.Resize:
            self._apply()
        return False


def install_frameless(window: QMainWindow) -> WindowTitleBar:
    """Strip the system frame; the returned title bar is placed by the caller."""
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    title_bar = WindowTitleBar(window)
    _install_edges(window)
    _RoundedMask(window)
    grip = QSizeGrip(window)
    grip.setObjectName("windowSizeGrip")
    grip.resize(16, 16)
    grip.move(window.width() - 16, window.height() - 16)
    grip.raise_()
    grip.show()
    title_bar.show()
    return title_bar
