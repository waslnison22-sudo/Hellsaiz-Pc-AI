"""Chat tests: legacy HTML helper plus the new widget-based transcript contracts."""

import pytest

from hellsaiz_pc_ai.app.chat_style import chat_bubble_html
from hellsaiz_pc_ai.app.theme import build_dark_stylesheet

try:  # chat_page pulls PySide6 GUI widgets (libEGL), absent on headless Linux runners.
    from hellsaiz_pc_ai.app.chat_page import ROLE_OBJECT_NAMES, TEXT_OBJECT_NAMES

    _CHAT_PAGE_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _CHAT_PAGE_AVAILABLE = False

_requires_chat_page = pytest.mark.skipif(
    not _CHAT_PAGE_AVAILABLE,
    reason="PySide6 GUI libraries are not available on this runner",
)


def test_legacy_assistant_bubble_keeps_accent_bar():
    html = chat_bubble_html("assistant", "Готово.")

    assert "border-left:3px solid #E8C29E" in html
    assert "Hellsaiz:" in html
    assert "Готово." in html


def test_legacy_helper_still_escapes_html_and_newlines():
    html = chat_bubble_html("assistant", "&lt;b&gt;first&lt;/b&gt;\nsecond")

    assert "&lt;b&gt;first&lt;/b&gt;" not in html
    assert "&amp;lt;b&amp;gt;first&amp;lt;/b&amp;gt;" in html
    assert "&lt;br&gt;" in html


def test_legacy_user_and_recognized_roles():
    user = chat_bubble_html("user", "открой блокнот")
    recognized = chat_bubble_html("recognized", "который час")

    assert "Вы:" in user
    assert "border-left" not in user
    assert "Распознано:" in recognized


@_requires_chat_page
def test_widget_roles_map_to_theme_object_names():
    assert ROLE_OBJECT_NAMES["user"] == "chatBubbleUser"
    assert ROLE_OBJECT_NAMES["assistant"] == "chatBubbleAssistant"
    assert ROLE_OBJECT_NAMES["system"] == "chatBubbleSystem"
    assert ROLE_OBJECT_NAMES["error"] == "chatBubbleError"
    assert TEXT_OBJECT_NAMES["user"] == "chatTextUser"
    assert TEXT_OBJECT_NAMES["assistant"] == "chatTextAssistant"


def test_theme_defines_chat_tokens_and_colours():
    stylesheet = build_dark_stylesheet()

    for selector in (
        "QFrame#chatBubbleUser",
        "QFrame#chatBubbleAssistant",
        "QFrame#chatBubbleSystem",
        "QLabel#chatTextUser",
        "QLabel#chatTextAssistant",
        "QLabel#chatTimestamp",
        "QLabel#chatTyping",
        "QPushButton#chatCopyButton",
        "QPushButton#chatClearButton",
        "QTextEdit#chatComposer",
        "QFrame#chatToast",
    ):
        assert selector in stylesheet

    assert "font-size: 17px" in stylesheet
    assert "font-size: 16px" in stylesheet
    assert "font-size: 12px" in stylesheet
    assert "border-bottom-right-radius: 4px" in stylesheet
    assert "border-bottom-left-radius: 4px" in stylesheet
    assert "#E8C29E" in stylesheet
