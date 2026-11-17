from hellsaiz_pc_ai.app.chat_style import chat_bubble_html


def test_assistant_bubble_has_accent_bar_and_name():
    html = chat_bubble_html("assistant", "Готово.")

    assert "border-left:3px solid #6d5df6" in html
    assert "Hellsaiz:" in html
    assert "Готово." in html


def test_user_bubble_is_neutral_and_labelled():
    html = chat_bubble_html("user", "открой блокнот")

    assert "Вы:" in html
    assert "открой блокнот" in html
    assert "border-left" not in html


def test_recognized_note_is_dim():
    html = chat_bubble_html("recognized", "который час")

    assert "Распознано:" in html
    assert "font-size:11px" in html


def test_html_is_escaped_and_newlines_preserved():
    html = chat_bubble_html("assistant", "<b>first</b>\nsecond")

    assert "<b>first</b>" not in html
    assert "&lt;b&gt;first&lt;/b&gt;" in html
    assert "<br>" in html


def test_unknown_role_renders_plain_paragraph():
    html = chat_bubble_html("unknown", "текст")

    assert html.startswith("<p>")
    assert "текст" in html
