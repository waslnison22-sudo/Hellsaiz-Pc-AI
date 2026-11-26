"""Micro-animations for the astra UI.

Qt stylesheets have no transitions, so hover and press feedback is animated
programmatically with QVariantAnimation on a color, and collapsible sections
ease their maximumHeight. Everything respects the system "reduce motion"
preference and never ticks while the widget is hidden.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

HOVER_DURATION_MS = 120
PRESS_DURATION_MS = 80
COLLAPSE_DURATION_MS = 160
PULSE_DURATION_MS = 1600
FAST_PULSE_DURATION_MS = 900


def reduce_motion() -> bool:
    """Return True when the OS asks applications to minimise motion."""
    instance = QGuiApplication.instance()
    if instance is None:
        return False
    try:
        hints = instance.styleHints()
    except (AttributeError, RuntimeError):
        return False
    accessor = getattr(hints, "reduceMotion", None)
    if not callable(accessor):
        return False
    try:
        return bool(accessor())
    except (RuntimeError, TypeError):
        return False


def animations_enabled(widget: QWidget | None = None) -> bool:
    """Animations run only for visible widgets and when motion is allowed."""
    if reduce_motion():
        return False
    if widget is None:
        return True
    parent = widget.parentWidget()
    return widget.isVisibleTo(parent) if parent is not None else widget.isVisible()


class ButtonFx(QObject):
    """Hover and press transitions for a themed QPushButton."""

    def __init__(
        self,
        widget: QWidget,
        base_color: str,
        hover_color: str,
        pressed_color: str,
    ) -> None:
        super().__init__(widget)
        self.widget = widget
        self.base_color = QColor(base_color)
        self.hover_color = QColor(hover_color)
        self.pressed_color = QColor(pressed_color)
        self._target = self.base_color
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(HOVER_DURATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._animation.valueChanged.connect(self._apply)
        widget.installEventFilter(self)
        self._last_painted: QColor | None = None
        widget.destroyed.connect(lambda *_: self._on_widget_destroyed())

    def _on_widget_destroyed(self, *_args: Any) -> None:
        # Qt may still deliver the last animation tick while the C++ widget is
        # already gone; stop early and drop the reference.
        try:
            self._animation.stop()
        except RuntimeError:
            pass
        self.widget = None

    def _apply(self, value: Any) -> None:
        if getattr(self, "widget", None) is None:
            return
        color = QColor(value) if not isinstance(value, QColor) else value
        if color == self._last_painted:
            return
        self._last_painted = color
        self.widget.setStyleSheet(
            f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
        )

    def _animate_to(self, color: QColor, duration: int = HOVER_DURATION_MS) -> None:
        if getattr(self, "widget", None) is None:
            return
        if not animations_enabled(self.widget):
            self._animation.stop()
            self._target = color
            self._apply(color)
            return
        self._target = color
        self._animation.stop()
        self._animation.setDuration(duration)
        self._animation.setStartValue(self._last_painted or self.base_color)
        self._animation.setEndValue(color)
        self._animation.start()

    def _restore(self) -> None:
        self._animation.stop()
        self._last_painted = None
        self.widget.setStyleSheet("")

    def eventFilter(self, watched: Any, event: QEvent) -> bool:  # noqa: N802 (Qt naming)
        if watched is self.widget:
            if event.type() == QEvent.Type.Enter:
                self._animate_to(self.hover_color)
            elif event.type() == QEvent.Type.Leave:
                self._restore()
            elif event.type() == QEvent.Type.MouseButtonPress:
                self._animate_to(self.pressed_color, PRESS_DURATION_MS)
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._animate_to(self.hover_color, PRESS_DURATION_MS)
            elif event.type() == QEvent.Type.Hide:
                self._animation.stop()
        return False


def install_button_fx(
    widget: QWidget,
    *,
    base: str = "#171716",
    hover: str = "#1F1F1D",
    pressed: str = "#121211",
) -> ButtonFx | None:
    """Attach hover/press feedback unless motion is disabled."""
    if reduce_motion():
        return None
    effect = ButtonFx(widget, base, hover, pressed)
    widget.setProperty("fxInstalled", True)
    return effect


def animate_height(widget: QWidget, expanded: bool, duration: int = COLLAPSE_DURATION_MS) -> None:
    """Ease a collapsible container between 0 and its natural height."""
    current = widget.maximumHeight()
    if expanded:
        widget.setVisible(True)
        widget.setMaximumHeight(0)
        target = max(0, widget.sizeHint().height())
        start = 0
    else:
        start = max(current, 0)
        target = 0
    if reduce_motion():
        widget.setMaximumHeight(target if expanded else 16777215)
        if not expanded:
            widget.setVisible(False)
        return
    animation = QPropertyAnimation(widget, b"maximumHeight", widget)
    animation.setDuration(duration)
    animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
    animation.setStartValue(start)
    animation.setEndValue(target)
    if not expanded:
        animation.finished.connect(lambda: widget.setVisible(False))
    else:
        animation.finished.connect(lambda: widget.setMaximumHeight(16777215))
    widget._collapse_animation = animation  # keep a reference alive
    animation.start()


def chevron_pixmap(angle: float, color: str = "#A6A29C", size: int = 16) -> QPixmap:
    """Small chevron rotated by ``angle`` degrees (0 = right, 90 = down)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.translate(size / 2.0, size / 2.0)
    painter.rotate(angle)
    painter.translate(-size / 2.0, -size / 2.0)
    pen = painter.pen()
    pen.setColor(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(int(size * 0.38), int(size * 0.28), int(size * 0.62), int(size * 0.50))
    painter.drawLine(int(size * 0.62), int(size * 0.50), int(size * 0.38), int(size * 0.72))
    painter.end()
    return pixmap


class ArrowRotator(QObject):
    """Smoothly rotate a chevron icon between collapsed and expanded states."""

    def __init__(self, widget: QWidget, size: int = 16) -> None:
        super().__init__(widget)
        self.widget = widget
        self.size = size
        self._angle = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(COLLAPSE_DURATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.valueChanged.connect(self._apply)
        self._paint(0.0)

    def _apply(self, value: Any) -> None:
        self._paint(float(value))

    def _paint(self, angle: float) -> None:
        self._angle = angle
        from PySide6.QtGui import QIcon

        self.widget.setIcon(QIcon(chevron_pixmap(angle, size=self.size)))
        self.widget.setIconSize(QSize(self.size, self.size))

    def set_expanded(self, expanded: bool) -> None:
        target = 90.0 if expanded else 0.0
        if reduce_motion():
            self._paint(target)
            return
        self._animation.stop()
        self._animation.setStartValue(self._angle)
        self._animation.setEndValue(target)
        self._animation.start()


class PulseDot(QObject):
    """Soft opacity pulse for the chat status dot; faster while thinking."""

    def __init__(self, label: QWidget, color: str = "#7dd487") -> None:
        super().__init__(label)
        self.label = label
        self.color = QColor(color)
        self._progress = 0.0
        self._step = 0.04
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(PULSE_DURATION_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.valueChanged.connect(self._apply)
        self._animation.finished.connect(self._loop)

    def _apply(self, value: Any) -> None:
        progress = float(value)
        alpha = 0.55 + 0.45 * (1.0 - abs(2.0 * progress - 1.0))
        self.label.setStyleSheet(
            f"color: rgba({self.color.red()}, {self.color.green()}, {self.color.blue()}, {int(alpha * 255)});"
            "font-size: 12px;"
        )

    def _loop(self) -> None:
        if not animations_enabled(self.label):
            return
        self._animation.setStartValue(1.0)
        self._animation.setEndValue(0.0)
        self._animation.start()

    def start(self) -> None:
        if reduce_motion() or not animations_enabled(self.label):
            return
        if self._animation.state() == QVariantAnimation.State.Running:
            return
        self._animation.start()

    def stop(self) -> None:
        self._animation.stop()

    def set_fast(self, fast: bool) -> None:
        self._animation.setDuration(FAST_PULSE_DURATION_MS if fast else PULSE_DURATION_MS)
