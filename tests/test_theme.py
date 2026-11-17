from hellsaiz_pc_ai.app.theme import build_dark_stylesheet


def test_dark_theme_has_visible_keyboard_focus_states():
    stylesheet = build_dark_stylesheet()

    assert "QPushButton:focus" in stylesheet
    assert "QListWidget#mainNavigation:focus" in stylesheet
    assert "QLineEdit:focus" in stylesheet


def test_theme_keeps_buttons_readable():
    stylesheet = build_dark_stylesheet()

    assert "min-height: 36px" in stylesheet
    assert "QTabBar::tab:selected" in stylesheet
    assert "QFrame#dashboardCard" in stylesheet
    assert "QLabel#dashboardCardValue" in stylesheet


def test_dark_theme_uses_accent_glass_over_the_wallpaper():
    stylesheet = build_dark_stylesheet()

    assert "QFrame#sidebar" in stylesheet
    assert "rgba(10, 13, 20, 168)" in stylesheet
    assert "rgba(7, 10, 15, 122)" in stylesheet
    assert "QWidget#wallpaperDim" in stylesheet
    assert "rgba(109, 93, 246" in stylesheet
    assert "QScrollBar::handle:vertical" in stylesheet
    assert "QLabel#statusError" in stylesheet
