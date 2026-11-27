"""Wave-9E chat contracts: designed column, alignment, visible bubbles, one prefix."""

from __future__ import annotations

import pytest

try:  # PySide6 widgets are unavailable on headless Linux runners.
    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.app.chat_page import (
        BUBBLE_MAX_CAP,
        CHAT_COLUMN_WIDTH,
        ChatTranscript,
        MessageBubble,
    )

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


def _transcript(app, width: int) -> ChatTranscript:
    transcript = ChatTranscript()
    transcript.resize(width, 600)
    transcript.show()
    app.processEvents()
    return transcript


@requires_qt
def test_chat_column_uses_the_designed_width():
    app = QApplication.instance() or QApplication([])
    transcript = _transcript(app, 1130)

    expected = max(280, min(CHAT_COLUMN_WIDTH, transcript.viewport().width()))

    assert transcript._column_widget.width() == expected
    assert transcript._column_widget.width() >= 660
    assert transcript._bubble_max_width() <= BUBBLE_MAX_CAP


@requires_qt
def test_chat_column_shrinks_on_a_narrow_window():
    app = QApplication.instance() or QApplication([])
    transcript = _transcript(app, 520)

    assert transcript._column_widget.width() >= 280
    assert transcript._column_widget.width() <= CHAT_COLUMN_WIDTH


@requires_qt
def test_rows_fill_the_column_and_keep_alignment():
    app = QApplication.instance() or QApplication([])
    transcript = _transcript(app, 1130)
    transcript.add_message("user", "Короткое сообщение", "12:00")
    transcript.add_message("assistant", "Ответ ассистента", "12:01")
    app.processEvents()

    bubbles = transcript.findChildren(MessageBubble)
    assert len(bubbles) == 2
    column_width = transcript._column_widget.width()
    for bubble in bubbles:
        assert bubble.width() == column_width, bubble.role
        frame = bubble.bubble
        if bubble.role == "user":
            assert frame.x() + frame.width() >= bubble.width() - 8
        else:
            assert frame.x() <= 8


@requires_qt
def test_new_bubbles_never_stay_invisible():
    app = QApplication.instance() or QApplication([])
    transcript = _transcript(app, 1130)
    bubble = transcript.add_message("assistant", "Проверка видимости", "12:02")

    ChatTranscript._force_visible(bubble)

    assert bubble.graphicsEffect() is None


@requires_qt
def test_recognition_prefix_is_not_duplicated():
    app = QApplication.instance() or QApplication([])
    transcript = _transcript(app, 1130)
    bubble = transcript.add_message("recognized", "Распознано: открой блокнот", "12:03")

    assert bubble.text_label.text() == "Распознано: открой блокнот"
