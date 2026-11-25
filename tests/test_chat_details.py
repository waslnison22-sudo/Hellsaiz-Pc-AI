"""P4-3 chat detail contracts: markup rendering and appear-animation guards."""

from __future__ import annotations

import pytest

from hellsaiz_pc_ai.app.chat_style import (
    chat_bubble_html,
    minute_changed,
    render_assistant_text,
)

try:  # PySide6 GUI libraries are absent on headless Linux runners.
    from PySide6.QtCore import QVariantAnimation
    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.app.chat_page import ChatTranscript

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

_requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


def test_assistant_bold_is_rendered_as_markup():
    html = render_assistant_text("Это **важно** и обычно.")

    assert "<b>важно</b>" in html
    assert "**" not in html


def test_assistant_inline_code_uses_monospace():
    html = render_assistant_text("Запусти `pip install` и повтори.")

    assert "<span style=" in html
    assert "monospace" in html
    assert "pip install" in html
    assert "`" not in html


def test_assistant_bullet_list_becomes_html_list():
    html = render_assistant_text("Варианты:\n- первый\n- второй")

    assert "<ul>" in html
    assert html.count("<li>") == 2
    assert "первый" in html and "второй" in html


def test_assistant_markup_escapes_html_first():
    html = render_assistant_text("<b>не тег</b> **жирный**")

    assert "&lt;b&gt;" in html
    assert "<b>жирный</b>" in html
    assert html.index("&lt;b&gt;") < html.index("<b>жирный</b>")


def test_user_text_is_not_interpreted():
    html = chat_bubble_html("user", "**не жирный** и `не код`")

    assert "**не жирный**" in html
    assert "`не код`" in html
    assert "<b>" not in html.replace("<b>Вы:</b>", "")


def test_minute_changed_stays_compatible():
    assert minute_changed(None, "21:03") is True
    assert minute_changed("21:03", "21:03") is False
    assert minute_changed("21:03", "21:04") is True


@_requires_qt
def test_appear_animation_stops_when_the_transcript_is_hidden():
    app = QApplication.instance() or QApplication([])
    transcript = ChatTranscript()
    transcript.show()
    app.processEvents()
    bubble = transcript.add_message("assistant", "Ответ", "21:05", "25.11.2026")
    app.processEvents()
    fade = getattr(bubble, "_appear_fade", None)

    assert fade is not None
    transcript.hide()
    app.processEvents()

    assert fade.state() != QVariantAnimation.State.Running
