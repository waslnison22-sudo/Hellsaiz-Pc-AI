from hellsaiz_pc_ai.app.theme import build_dark_stylesheet


def test_dark_theme_has_visible_keyboard_focus_states():
    stylesheet = build_dark_stylesheet()

    assert "QPushButton:focus" in stylesheet
    assert "QTabBar::tab:selected" in stylesheet
    assert "QLineEdit:focus" in stylesheet


def test_theme_keeps_buttons_readable():
    stylesheet = build_dark_stylesheet()

    assert "min-height: 36px" in stylesheet
    assert "QTabBar::tab:selected" in stylesheet
    assert "QFrame#dashboardCard" in stylesheet
    assert "QLabel#dashboardCardValue" in stylesheet


def test_dark_theme_uses_the_astra_palette():
    stylesheet = build_dark_stylesheet()

    assert "#0B0B0B" in stylesheet
    assert "#171716" in stylesheet
    assert "QWidget#wallpaperDim" in stylesheet
    assert "rgba(232, 194, 158" in stylesheet
    assert "#E8C29E" in stylesheet
    assert "#A6A29C" in stylesheet
    assert "QScrollBar::handle:vertical" in stylesheet
    assert "QLabel#statusError" in stylesheet


def test_top_bar_navigation_styles_are_present():
    stylesheet = build_dark_stylesheet()

    assert "QPushButton#navPill" in stylesheet
    assert "QPushButton#navPill:checked" in stylesheet
    assert "QWidget#topBar" in stylesheet
    assert "QPushButton#ghostButton" in stylesheet


def test_collapsible_section_style_is_present():
    stylesheet = build_dark_stylesheet()

    assert "QToolButton#collapsibleHeader" in stylesheet
    assert "QToolButton#collapsibleHeader:hover" in stylesheet
