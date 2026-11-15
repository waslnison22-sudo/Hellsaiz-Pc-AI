from hellsaiz_pc_ai.app.theme import build_dark_stylesheet


def test_dark_theme_has_visible_keyboard_focus_states():
    stylesheet = build_dark_stylesheet()

    assert "QPushButton:focus" in stylesheet
    assert "QListWidget#mainNavigation:focus" in stylesheet
    assert "QLineEdit:focus" in stylesheet


def test_dark_theme_keeps_the_monochrome_glass_visual_language():
    stylesheet = build_dark_stylesheet()

    assert "QFrame#sidebar" in stylesheet
    assert "rgba(10, 14, 20, 224)" in stylesheet
    assert "QScrollBar::handle:vertical" in stylesheet
    assert "#f7f9fc" in stylesheet
