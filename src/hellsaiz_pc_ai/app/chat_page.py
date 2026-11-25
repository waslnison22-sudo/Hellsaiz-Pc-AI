"""Chat transcript widgets for the wave-4 redesign (bubbles, typing, input, toast)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ROLE_OBJECT_NAMES = {
    "user": "chatBubbleUser",
    "assistant": "chatBubbleAssistant",
    "system": "chatBubbleSystem",
    "meta": "chatBubbleMeta",
    "error": "chatBubbleError",
}

TEXT_OBJECT_NAMES = {
    "user": "chatTextUser",
    "assistant": "chatTextAssistant",
    "system": "chatTextSystem",
    "meta": "chatTextMeta",
    "error": "chatTextError",
}


class MessageBubble(QWidget):
    """One message: bubble frame, hover copy button and a timestamp under it."""

    copied = Signal(str)

    def __init__(
        self,
        role: str,
        text: str,
        timestamp: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        self._text = text
        self.setObjectName("chatMessageRow")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(2)

        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)
        bubble_row.setSpacing(6)

        self.bubble = QFrame()
        self.bubble.setObjectName(ROLE_OBJECT_NAMES.get(role, "chatBubbleAssistant"))
        self.bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        self.text_label = QLabel(text)
        self.text_label.setObjectName(TEXT_OBJECT_NAMES.get(role, "chatTextAssistant"))
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble_layout.addWidget(self.text_label)

        self.copy_button = QPushButton("\u29c9")
        self.copy_button.setObjectName("chatCopyButton")
        self.copy_button.setToolTip("Скопировать сообщение")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.setFixedSize(24, 24)
        self.copy_button.hide()
        self.copy_button.clicked.connect(self._copy)

        if role == "user":
            bubble_row.addStretch(1)
            bubble_row.addWidget(self.copy_button)
            bubble_row.addWidget(self.bubble)
        else:
            bubble_row.addWidget(self.bubble)
            bubble_row.addWidget(self.copy_button)
            bubble_row.addStretch(1)
        column.addLayout(bubble_row)

        self.timestamp_label = QLabel(timestamp)
        self.timestamp_label.setObjectName("chatTimestamp")
        timestamp_row = QHBoxLayout()
        timestamp_row.setContentsMargins(2, 0, 2, 0)
        if role == "user":
            timestamp_row.addStretch(1)
            timestamp_row.addWidget(self.timestamp_label)
        else:
            timestamp_row.addWidget(self.timestamp_label)
            timestamp_row.addStretch(1)
        column.addLayout(timestamp_row)

        row.addLayout(column, 1)

    def _copy(self) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(self._text)
        self.copied.emit(self._text)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        self.copy_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        self.copy_button.hide()
        super().leaveEvent(event)


TYPING_REVEAL_DELAY_MS = 300


class TypingIndicator(QWidget):
    """Assistant bubble with animated dots, shown while the worker answers.

    The dot cycle is intentionally short: the indicator is only a hint that the
    answer is coming, and a slow animation reads as a freeze on a busy machine.
    """

    TIMER_INTERVAL_MS = 150
    DOTS_STATES = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        bubble = QFrame()
        bubble.setObjectName("chatBubbleAssistant")
        bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        bubble_layout = QHBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        self.label = QLabel("Ассистент печатает")
        self.label.setObjectName("chatTyping")
        bubble_layout.addWidget(self.label)
        row.addWidget(bubble)
        row.addStretch(1)
        self._dots = 0
        self._timer = QTimer(self)
        self._timer.setInterval(self.TIMER_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._dots = 0
        self._tick()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._dots = (self._dots + 1) % self.DOTS_STATES
        self.label.setText("Ассистент печатает" + "." * self._dots)


class ChatTranscript(QScrollArea):
    """Scrollable message list with sticky-to-bottom behaviour."""

    copied = Signal(str)
    # Hard cap on visible bubbles: beyond this, oldest bubbles are dropped so a
    # long session cannot grow the widget tree without bound. Persisted history
    # is unaffected (ChatStore keeps the full log).
    MAX_VISIBLE_MESSAGES = 300

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("chatTranscript")

        container = QWidget()
        container.setObjectName("chatTranscriptBody")
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(4, 8, 4, 8)
        self._layout.setSpacing(10)
        self._layout.addStretch(1)
        self.setWidget(container)

        self._typing = TypingIndicator()
        self._typing.hide()
        self._typing_reveal = QTimer(self)
        self._typing_reveal.setSingleShot(True)
        self._typing_reveal.timeout.connect(self._reveal_typing)
        self._bubbles: list[MessageBubble] = []
        self._stick_to_bottom = True
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    def _on_range_changed(self, _minimum: int, maximum: int) -> None:
        if self._stick_to_bottom:
            self.verticalScrollBar().setValue(maximum)

    def _on_scrolled(self, value: int) -> None:
        bar = self.verticalScrollBar()
        self._stick_to_bottom = value >= bar.maximum() - 48

    def add_message(self, role: str, text: str, timestamp: str) -> MessageBubble:
        stick = self._is_at_bottom()
        if self._typing.isVisible():
            self._layout.removeWidget(self._typing)
            self._typing.hide()
        bubble = MessageBubble(role, text, timestamp)
        bubble.copied.connect(self.copied)
        bubble.setMaximumWidth(self._bubble_max_width())
        self._bubbles.append(bubble)
        self._layout.addWidget(bubble)
        self._layout.addWidget(self._typing)
        self._trim_overflow()
        if stick:
            QTimer.singleShot(0, self.scroll_to_bottom)
        return bubble

    def _trim_overflow(self) -> None:
        while len(self._bubbles) > self.MAX_VISIBLE_MESSAGES:
            bubble = self._bubbles.pop(0)
            self._layout.removeWidget(bubble)
            bubble.deleteLater()

    def show_typing(self) -> None:
        # Short answers should not flash the indicator: reveal it only after a
        # small delay, and cancel the reveal when the reply arrives first.
        self._typing_reveal.start(TYPING_REVEAL_DELAY_MS)

    def _reveal_typing(self) -> None:
        stick = self._is_at_bottom()
        if self._layout.indexOf(self._typing) == -1:
            self._layout.addWidget(self._typing)
        else:
            self._layout.removeWidget(self._typing)
            self._layout.addWidget(self._typing)
        self._typing.show()
        self._typing.start()
        if stick:
            QTimer.singleShot(0, self.scroll_to_bottom)

    def hide_typing(self) -> None:
        self._typing_reveal.stop()
        self._typing.stop()
        self._typing.hide()

    def clear_messages(self) -> list[MessageBubble]:
        removed = list(self._bubbles)
        for bubble in removed:
            self._layout.removeWidget(bubble)
            bubble.hide()
        self._bubbles.clear()
        self.hide_typing()
        return removed

    def restore_messages(self, bubbles: list[MessageBubble]) -> None:
        for bubble in bubbles:
            bubble.show()
            self._layout.addWidget(bubble)
            self._bubbles.append(bubble)
        self.scroll_to_bottom()

    def message_count(self) -> int:
        return len(self._bubbles)

    def scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _is_at_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 48

    def _bubble_max_width(self) -> int:
        width = self.viewport().width() or self.width()
        return max(240, int(width * 0.7))

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        limit = self._bubble_max_width()
        for bubble in self._bubbles:
            bubble.setMaximumWidth(limit)


class ChatInput(QTextEdit):
    """One-line composer that grows to four lines; Enter sends, Shift+Enter breaks."""

    submitted = Signal(str)
    _LINE_HEIGHT = 22
    _MAX_LINES = 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatComposer")
        self.setAcceptRichText(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.textChanged.connect(self._fit_height)
        self._fit_height()

    def text(self) -> str:  # noqa: N802 (Qt-compatible name used by callers)
        return self.toPlainText()

    def setText(self, value: str) -> None:  # noqa: N802 (Qt-compatible name)
        self.setPlainText(value)
        self._fit_height()

    def clear(self) -> None:
        self.setPlainText("")
        self._fit_height()

    def _fit_height(self) -> None:
        document_height = int(self.document().size().height())
        lines = max(1, min(self._MAX_LINES, (document_height + self._LINE_HEIGHT - 1) // self._LINE_HEIGHT))
        height = lines * self._LINE_HEIGHT + 16
        self.setFixedHeight(height)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if lines >= self._MAX_LINES
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def keyPressEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            text = self.text().strip()
            if not text:
                return
            self.submitted.emit(text)
            return
        super().keyPressEvent(event)


class Toast(QFrame):
    """Small floating notice with an optional action button and a fade-out."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("chatToast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)
        self.label = QLabel("")
        self.label.setObjectName("chatToastText")
        layout.addWidget(self.label)
        self.action = QPushButton("")
        self.action.setObjectName("chatToastAction")
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.hide()
        layout.addWidget(self.action)
        self._action_callback: Callable[[], None] | None = None
        self.action.clicked.connect(self._run_action)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(
        self,
        text: str,
        *,
        action_text: str = "",
        action: Callable[[], None] | None = None,
        timeout_ms: int = 1600,
    ) -> None:
        parent = self.parentWidget()
        # Non-action toasts are pure notices: let clicks fall through to the UI
        # underneath instead of swallowing them.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not action_text)
        limit = max(220, int((parent.width() if parent is not None else 480) - 80))
        self.setMaximumWidth(limit)
        inner = max(120, limit - 28 - (110 if action_text else 0))
        self.label.setMaximumWidth(inner)
        if len(text) > 220:
            text = text[:217].rstrip() + "…"
        self.label.setWordWrap(True)
        self.label.setText(text)
        self._action_callback = action
        if action_text:
            self.action.setText(action_text)
            self.action.show()
        else:
            self.action.hide()
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._effect.setEnabled(True)
        self._effect.setOpacity(0.0)
        self._fade.stop()
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._hide_timer.start(timeout_ms)

    def _on_fade_finished(self) -> None:
        # Drop the opacity effect once visible so the widget renders normally
        # (QGraphicsOpacityEffect is not always painted into grab()/screenshots).
        if self._effect.opacity() >= 0.99:
            self._effect.setEnabled(False)
        else:
            self.hide()

    def _run_action(self) -> None:
        callback = self._action_callback
        self._action_callback = None
        self._hide_timer.stop()
        self.hide()
        if callback is not None:
            callback()

    def _fade_out(self) -> None:
        self._effect.setEnabled(True)
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 16
        self.move(max(8, x), max(8, y))
