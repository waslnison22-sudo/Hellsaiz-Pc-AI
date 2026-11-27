"""Wave-7 batch 6 contracts: knice chat geometry and greeting."""

from __future__ import annotations

import inspect

import pytest

from hellsaiz_pc_ai.app.theme import build_dark_stylesheet

try:  # The widget module imports PySide6 — unavailable on headless Linux runners.
    from hellsaiz_pc_ai.app import chat_page as chat_module
except ImportError:  # pragma: no cover - runner-specific
    chat_module = None

requires_chat_module = pytest.mark.skipif(
    chat_module is None,
    reason="PySide6-backed chat module is not available on this runner",
)


@requires_chat_module
def test_knice_chat_geometry_constants():
    # Owner pass 4: the chat fills the page, so the column and the bubble cap grew.
    assert chat_module.CHAT_COLUMN_WIDTH == 900
    assert chat_module.BUBBLE_MAX_RATIO == 0.92
    assert chat_module.BUBBLE_MAX_CAP == 640


@requires_chat_module
def test_greeting_brand_and_prompt():
    assert chat_module.ChatGreeting.BRAND_TEXT == "Хеллсайз"
    assert chat_module.ChatGreeting.BRAND_FONT_SIZE == 44
    assert chat_module.ChatGreeting.PROMPT_TEXT == "пиши сюда — или просто скажи вслух"
    source = inspect.getsource(chat_module)
    assert "GradientBrandLabel" in source
    assert "chatGreetingPrompt" in source


@requires_chat_module
def test_bubbles_have_no_avatars_and_knice_padding():
    source = inspect.getsource(chat_module.MessageBubble)
    assert "chatAvatarUser" not in source
    assert "chatAvatarAssistant" not in source
    assert "setContentsMargins(18, 12, 18, 12)" in source


@requires_chat_module
def test_transcript_uses_the_narrow_column_and_overlay_greeting():
    source = inspect.getsource(chat_module.ChatTranscript)
    assert "CHAT_COLUMN_WIDTH" in source
    assert "_greeting_overlay" in source
    assert "setSpacing(16)" in source


def test_theme_carries_knice_chat_tokens():
    stylesheet = build_dark_stylesheet()
    user_block = stylesheet.rsplit("QFrame#chatBubbleUser {", 1)[1].split("}", 1)[0]
    assistant_block = stylesheet.rsplit("QFrame#chatBubbleAssistant {", 1)[1].split("}", 1)[0]
    composer_block = stylesheet.rsplit("QTextEdit#chatComposer {", 1)[1].split("}", 1)[0]
    user_text = stylesheet.rsplit("QLabel#chatTextUser {", 1)[1].split("}", 1)[0]
    assistant_text = stylesheet.rsplit("QLabel#chatTextAssistant {", 1)[1].split("}", 1)[0]

    assert "border-radius: 16px" in user_block
    assert "border-bottom-right-radius" not in user_block
    assert "border-radius: 16px" in assistant_block
    assert "border-top-left-radius" not in assistant_block
    # Wave 9E: the assistant bubble has no hand-made hairline border.
    assert "border-top:" not in assistant_block
    assert "border-radius: 16px" in composer_block
    assert "padding: 10px 16px" in composer_block
    assert "font-size: 16px" in user_text
    assert "font-size: 16px" in assistant_text
    assert "QLabel#chatGreetingPrompt" in stylesheet
