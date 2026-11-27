"""Chat transcript widgets for the wave-4/6 redesign (bubbles, typing, input, toast).

Wave 6 (knice): a 680 px message column, 16 px bubbles with a "broken" corner,
no avatars inside bubbles (the header keeps the only avatar) and a knice-style
greeting shown while the chat is empty.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    Qt,
    QSize,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from hellsaiz_pc_ai.app.chat_style import minute_changed, render_assistant_text
from hellsaiz_pc_ai.app.ui_fx import animations_enabled, reduce_motion

from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
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

# knice chat geometry: the messages live in a narrow centred column; bubbles
# never exceed 85% of it (capped at 580 px for very wide windows).
CHAT_COLUMN_WIDTH = 900
BUBBLE_MAX_RATIO = 0.92
BUBBLE_MAX_CAP = 640


class GradientBrandLabel(QWidget):
    """Brand wordmark with a vertical text gradient (QSS cannot clip text)."""

    def __init__(
        self,
        text: str,
        font_size: int = 48,
        align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._font_size = font_size
        self._align = align
        font = QFont()
        font.setPixelSize(font_size)
        font.setWeight(QFont.Weight.ExtraBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -1.0)
        self._font = font

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(self._font)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.2, QColor("#F2EFEA"))
        gradient.setColorAt(1.0, QColor("#9B9CA3"))
        painter.setPen(QPen(gradient, 0))
        painter.drawText(
            self.rect(), self._align | Qt.AlignmentFlag.AlignVCenter, self._text
        )

    def sizeHint(self):  # noqa: N802 (Qt naming)
        metrics = QFontMetrics(self._font)
        return metrics.boundingRect(self._text).size() + QSize(0, 8)


class ChatGreeting(QWidget):
    """Empty-chat greeting: gradient brand wordmark plus a hand-written prompt."""

    BRAND_TEXT = "Хеллсайз"
    BRAND_FONT_SIZE = 44
    PROMPT_TEXT = "пиши сюда — или просто скажи вслух"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatGreeting")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.brand = GradientBrandLabel(self.BRAND_TEXT, self.BRAND_FONT_SIZE)
        self.brand.setFixedHeight(int(self.BRAND_FONT_SIZE * 1.2))
        layout.addWidget(self.brand)
        self.prompt = QLabel(self.PROMPT_TEXT)
        self.prompt.setObjectName("chatGreetingPrompt")
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.prompt)


class MessageBubble(QWidget):
    """One message: bubble frame, hover copy button and a timestamp under it.

    Wave 6: avatars are gone (the header owns the only avatar) and the bubble
    uses knice padding with a 16 px radius and a "broken" corner.
    """

    copied = Signal(str)

    def __init__(
        self,
        role: str,
        text: str,
        timestamp: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.role = role
        self._text = text
        self.setObjectName("chatMessageRow")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

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
        bubble_layout.setContentsMargins(18, 12, 18, 12)
        self.text_label = QLabel()
        self.text_label.setObjectName(TEXT_OBJECT_NAMES.get(role, "chatTextAssistant"))
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if role == "recognized":
            self.text_label.setTextFormat(Qt.TextFormat.PlainText)
            clean = text.strip()
            if clean.casefold().startswith("распознано:"):
                clean = clean.split(":", 1)[1].strip()
            self.text_label.setText(f"Распознано: {clean}")
        elif role == "assistant":
            self.text_label.setTextFormat(Qt.TextFormat.RichText)
            self.text_label.setText(render_assistant_text(text))
        else:
            self.text_label.setTextFormat(Qt.TextFormat.PlainText)
            self.text_label.setText(text)
        bubble_layout.addWidget(self.text_label)
        if role in {"assistant", "user"} and not reduce_motion_enabled():
            shadow = QGraphicsDropShadowEffect(self.bubble)
            shadow.setBlurRadius(18)
            shadow.setOffset(0, 3)
            shadow.setColor(
                QColor(0, 0, 0, 51) if role == "assistant" else QColor(232, 194, 158, 40)
            )
            self.bubble.setGraphicsEffect(shadow)

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

        self.timestamp_label: QLabel | None = None
        if timestamp:
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

    def set_timestamp_visible(self, visible: bool) -> None:
        """Group timestamps: only the first bubble of a minute shows the time."""
        if self.timestamp_label is None:
            return
        self.timestamp_label.setVisible(visible)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        self.copy_button.show()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        self.copy_button.hide()
        super().leaveEvent(event)


TYPING_REVEAL_DELAY_MS = 300


def reduce_motion_enabled() -> bool:
    """Shadow and appear-animation are skipped when motion is reduced."""
    return reduce_motion()


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
        bubble_layout.setContentsMargins(18, 12, 18, 12)
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
    """Scrollable message list with sticky-to-bottom behaviour.

    Wave 6: the content lives in a centred 680 px column and an empty chat
    shows the knice-style greeting overlay above the composer area.
    """

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
        outer = QHBoxLayout(container)
        outer.setContentsMargins(0, 8, 0, 8)
        outer.setSpacing(0)
        outer.addStretch(1)
        # A real column widget with the designed width: a bare layout shrank to
        # its content, and the bubbles sat in a narrow strip in the middle.
        column_widget = QWidget()
        column_widget.setObjectName("chatTranscriptColumn")
        column_widget.setFixedWidth(CHAT_COLUMN_WIDTH)
        column = QVBoxLayout(column_widget)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(16)
        self._column = column
        self._column_widget = column_widget
        outer.addWidget(column_widget, 0)
        outer.addStretch(1)
        self._layout = column  # legacy alias: the messages column
        self.setWidget(container)

        self._typing = TypingIndicator()
        self._typing.hide()
        self._typing_reveal = QTimer(self)
        self._typing_reveal.setSingleShot(True)
        self._typing_reveal.timeout.connect(self._reveal_typing)
        self._bubbles: list[MessageBubble] = []
        self._last_minute: str | None = None
        self._last_day: str | None = None
        self._last_bubble: MessageBubble | None = None
        self._stick_to_bottom = True

        # knice-style greeting for an empty chat, kept as an overlay so it
        # never interferes with the message flow inside the scroll column.
        self._greeting_overlay = ChatGreeting(self)
        self._greeting_overlay.hide()

        # "↓ новые сообщения" pill shown while the user reads older messages.
        self._new_messages_button = QPushButton("↓ новые сообщения", self)
        self._new_messages_button.setObjectName("newMessagesButton")
        self._new_messages_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_messages_button.hide()
        self._new_messages_button.clicked.connect(self._jump_to_bottom)
        self.verticalScrollBar().rangeChanged.connect(self._on_range_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    def _designed_column_width(self) -> int:
        """min(CHAT_COLUMN_WIDTH, 85 % of the viewport), never below 280 px."""
        available = int((self.viewport().width() or self.width()) * BUBBLE_MAX_RATIO)
        return max(280, min(CHAT_COLUMN_WIDTH, available))

    def _on_range_changed(self, _minimum: int, maximum: int) -> None:
        if self._stick_to_bottom:
            self.verticalScrollBar().setValue(maximum)

    def _on_scrolled(self, value: int) -> None:
        bar = self.verticalScrollBar()
        self._stick_to_bottom = value >= bar.maximum() - 48

    def add_message(
        self,
        role: str,
        text: str,
        timestamp: str,
        day: str | None = None,
    ) -> MessageBubble:
        stick = self._is_at_bottom()
        if self._typing.isVisible():
            self._column.removeWidget(self._typing)
            self._typing.hide()

        # Day divider above the first message of a new day.
        day_label = day or datetime.now().strftime("%d.%m.%Y")
        if self._last_day != day_label:
            self._last_day = day_label
            today = datetime.now().strftime("%d.%m.%Y")
            header = QLabel("Сегодня" if day_label == today else day_label)
            header.setObjectName("chatDayDivider")
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._column.addWidget(header)
            divider = QWidget()
            divider.setObjectName("chatDayDividerSpacer")
            divider.setFixedHeight(2)
            self._column.addWidget(divider)

        # Messenger-style grouping: the first bubble of a minute keeps the time,
        # and a fresh bubble in the same minute takes it over (last message always
        # shows the time).
        same_minute = not minute_changed(self._last_minute, timestamp)
        if same_minute and self._last_bubble is not None:
            self._last_bubble.set_timestamp_visible(False)
        self._last_minute = timestamp
        bubble = MessageBubble(role, text, timestamp)
        bubble.copied.connect(self.copied)
        bubble.bubble.setMaximumWidth(self._bubble_max_width())
        self._bubbles.append(bubble)
        self._last_bubble = bubble
        self._column.addWidget(bubble)
        self._column.addWidget(self._typing)
        self._trim_overflow()
        self._animate_appear(bubble)
        if self._greeting_overlay.isVisible():
            self._greeting_overlay.hide()
        if stick:
            self._smooth_scroll_to_bottom()
            self._new_messages_button.hide()
        else:
            self._pending_new_message = True
            self._new_messages_button.show()
            self._reposition_new_messages_button()
        return bubble

    @staticmethod
    def _force_visible(bubble: MessageBubble) -> None:
        """Drop a leftover opacity effect so the bubble paints at 100 %."""
        if bubble.graphicsEffect() is None:
            return
        try:
            bubble.setGraphicsEffect(None)
        except RuntimeError:
            return

    def _animate_appear(self, bubble: MessageBubble) -> None:
        """120 ms fade-in with an 8 px upward drift; skipped when motion is reduced."""
        if not animations_enabled(self):
            return
        effect = QGraphicsOpacityEffect(bubble)
        effect.setOpacity(0.0)
        bubble.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", bubble)
        fade.setDuration(120)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutQuad)
        drift = QVariantAnimation(bubble)
        drift.setDuration(120)
        drift.setStartValue(8)
        drift.setEndValue(0)
        drift.setEasingCurve(QEasingCurve.Type.OutQuad)

        def apply_drift(value) -> None:
            bubble.setContentsMargins(0, int(value), 0, 0)

        drift.valueChanged.connect(apply_drift)
        drift.finished.connect(lambda: bubble.setContentsMargins(0, 0, 0, 0))

        def finish_appear() -> None:
            # setGraphicsEffect(None) takes ownership back and deletes the effect;
            # calling effect.deleteLater() on top of it double-frees the object.
            ChatTranscript._force_visible(bubble)

        fade.finished.connect(finish_appear)
        bubble._appear_fade = fade
        bubble._appear_drift = drift
        fade.start()
        drift.start()
        # Safety net: never leave a bubble invisible when the animation is cut
        # short (page switch, clear, grab, reduced motion at runtime).
        QTimer.singleShot(400, lambda: ChatTranscript._force_visible(bubble))

    def _smooth_scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        target = bar.maximum()
        if not animations_enabled(self) or bar.value() == target:
            bar.setValue(target)
            return
        animation = QPropertyAnimation(bar, b"value", self)
        animation.setDuration(150)
        animation.setStartValue(bar.value())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._scroll_animation = animation
        animation.start()

    def _jump_to_bottom(self) -> None:
        self._smooth_scroll_to_bottom()
        self._pending_new_message = False
        self._new_messages_button.hide()

    def _reposition_new_messages_button(self) -> None:
        button = self._new_messages_button
        button.adjustSize()
        x = max(0, (self.viewport().width() - button.width()) // 2)
        y = max(0, self.viewport().height() - button.height() - 12)
        button.move(x, y)
        button.raise_()

    def _reposition_greeting_overlay(self) -> None:
        overlay = self._greeting_overlay
        overlay.adjustSize()
        x = max(0, (self.viewport().width() - overlay.width()) // 2)
        # The brand reads as a page heading: a bit above the middle, not at the bottom.
        available = max(0, self.viewport().height() - overlay.height())
        y = max(24, int(available * 0.32))
        overlay.move(x, y)
        overlay.raise_()

    def _trim_overflow(self) -> None:
        while len(self._bubbles) > self.MAX_VISIBLE_MESSAGES:
            bubble = self._bubbles.pop(0)
            for attribute in ("_appear_fade", "_appear_drift"):
                animation = getattr(bubble, attribute, None)
                if animation is not None:
                    animation.stop()
            self._column.removeWidget(bubble)
            bubble.deleteLater()

    def show_typing(self) -> None:
        # Short answers should not flash the indicator: reveal it only after a
        # small delay, and cancel the reveal when the reply arrives first.
        self._typing_reveal.start(TYPING_REVEAL_DELAY_MS)

    def _reveal_typing(self) -> None:
        stick = self._is_at_bottom()
        if self._column.indexOf(self._typing) == -1:
            self._column.addWidget(self._typing)
        else:
            self._column.removeWidget(self._typing)
            self._column.addWidget(self._typing)
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
            for attribute in ("_appear_fade", "_appear_drift"):
                animation = getattr(bubble, attribute, None)
                if animation is not None:
                    animation.stop()
            self._column.removeWidget(bubble)
            bubble.hide()
        self._bubbles.clear()
        self._last_minute = None
        self._last_day = None
        self._last_bubble = None
        self._pending_new_message = False
        self._new_messages_button.hide()
        self.hide_typing()
        self._greeting_overlay.show()
        self._reposition_greeting_overlay()
        return removed

    def restore_messages(self, bubbles: list[MessageBubble]) -> None:
        for bubble in bubbles:
            bubble.show()
            self._column.addWidget(bubble)
            self._bubbles.append(bubble)
        if self._greeting_overlay.isVisible():
            self._greeting_overlay.hide()
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
        column = self._designed_column_width()
        return max(240, min(BUBBLE_MAX_CAP, int(column * BUBBLE_MAX_RATIO)))

    def showEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        # An empty chat greets; the overlay lives outside the scrolled column.
        if not self._bubbles:
            self._greeting_overlay.show()
            self._reposition_greeting_overlay()

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        super().hideEvent(event)
        self._new_messages_button.hide()
        for bubble in self._bubbles:
            for attribute in ("_appear_fade", "_appear_drift"):
                animation = getattr(bubble, attribute, None)
                if animation is not None:
                    animation.stop()

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        column_widget = getattr(self, "_column_widget", None)
        if column_widget is not None:
            width = self._designed_column_width()
            if column_widget.width() != width:
                column_widget.setFixedWidth(width)
        self._reposition_new_messages_button()
        limit = self._bubble_max_width()
        for bubble in self._bubbles:
            bubble.bubble.setMaximumWidth(limit)
        if self._greeting_overlay.isVisible():
            self._reposition_greeting_overlay()


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

    def _fade_out(self) -> None:
        """Fade the notice out; _on_fade_finished hides it at the end."""
        if not self.isVisible():
            return
        self._effect.setEnabled(True)
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _run_action(self) -> None:
        callback = self._action_callback
        self._action_callback = None
        self._hide_timer.stop()
        self.hide()
        if callback is not None:
            callback()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 16
        self.move(max(8, x), max(8, y))
