"""Reusable HUD primitives for the wave-3 visual layer.

All widgets stay presentation-only: no business logic, no threads, no I/O.
"""

from __future__ import annotations
import logging

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    QTimer,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsOpacityEffect,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class SectionCard(QFrame):
    """Glass card with a small uppercase title and optional body widget."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        self._title_label = QLabel(title)
        self._title_label.setObjectName("dashboardCardTitle")
        layout.addWidget(self._title_label)

    def add_body(self, widget: QWidget, stretch: int = 1) -> None:
        self.layout().addWidget(widget, stretch)


class ToggleSwitch(QAbstractButton):
    """Rounded toggle with a sliding knob, as in the HUD mockup."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Переключить настройку")
        self._knob_position = 3.0
        self._knob_animation = QPropertyAnimation(self, b"knobPosition", self)
        self._knob_animation.setDuration(190)
        self._knob_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_knob)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(44, 26)

    def nextCheckState(self) -> None:  # noqa: N802 (Qt naming)
        self.setChecked(not self.isChecked())

    def _animate_knob(self, checked: bool) -> None:
        self._knob_animation.setStartValue(self._knob_position)
        self._knob_animation.setEndValue(21.0 if checked else 3.0)
        self._knob_animation.start()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        checked = self.isChecked()
        track = QColor("#E8C29E") if checked else QColor("#1F1F1D")
        border = QColor("#D9A87C") if checked else QColor("rgba(255, 255, 255, 40)")
        painter.setPen(QPen(border, 1))
        painter.setBrush(track)
        painter.drawRoundedRect(1, 1, 40, 22, 11, 11)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1A140F") if checked else QColor("#A6A29C"))
        painter.drawEllipse(int(self._knob_position), 4, 16, 16)

    def get_knob_position(self) -> float:
        return self._knob_position

    def set_knob_position(self, value: float) -> None:
        self._knob_position = value
        self.update()

    knobPosition = Property(float, get_knob_position, set_knob_position)


class StatChip(QLabel):
    """Small status badge: ok / warn / err with a glowing bullet."""

    LEVEL_OBJECT_NAMES = {
        "ok": "statChipOk",
        "warn": "statChipWarn",
        "err": "statChipErr",
    }

    def __init__(self, text: str, level: str = "ok", parent: QWidget | None = None) -> None:
        super().__init__(f"● {text}", parent)
        self.setObjectName(self.LEVEL_OBJECT_NAMES.get(level, "statChipOk"))
        self.setToolTip("Текущее состояние")


class EmptyState(QFrame):
    """Friendly placeholder with a glyph, a title, a hint and an optional action."""

    def __init__(
        self,
        title: str,
        hint: str,
        glyph: str = "🔔",
        action_text: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        logging.info("EmptyState ctor: entered.")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 16)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph_label = QLabel(glyph)
        glyph_label.setObjectName("emptyStateGlyph")
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(glyph_label)
        logging.info("EmptyState ctor: glyph label added.")
        title_label = QLabel(title)
        title_label.setObjectName("emptyStateTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        hint_label = QLabel(hint)
        hint_label.setObjectName("emptyStateHint")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
        self.action_button: QPushButton | None = None
        if action_text:
            self.action_button = QPushButton(action_text)
            self.action_button.setObjectName("primaryButton")
            layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignCenter)
        logging.info("EmptyState ctor: done.")


class PageFader(QStackedWidget):
    """QStackedWidget with a soft fade on page switch (no layout thrash)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fade_duration = 160
        self._previous_index = -1
        self.currentChanged.connect(self._fade_current)

    def _fade_current(self, _index: int) -> None:
        if self._previous_index < 0:
            # First page selection at startup: no fade, keep the launch clean.
            self._previous_index = self.currentIndex()
            return
        self._previous_index = self.currentIndex()
        widget = self.currentWidget()
        if widget is None:
            return
        fade_in(widget, duration=self._fade_duration)


def fade_in(widget: QWidget, duration: int = 160, delay_ms: int = 0):
    """Fade a widget in; safe for repeated calls."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setDuration(duration)
    animation.setStartValue(0.0)
    animation.setEndValue(1.0)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    if delay_ms > 0:
        QTimer.singleShot(delay_ms, animation.start)
    else:
        animation.start()
    return animation
