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


def test_glass_panel_tokens_and_selectors_exist():
    from hellsaiz_pc_ai.app.theme import (
        GLASS_BG,
        GLASS_BORDER,
        GLASS_HIGHLIGHT,
        GLASS_RADIUS,
    )

    stylesheet = build_dark_stylesheet()

    assert "QFrame#glassPanel" in stylesheet
    assert "QWidget#glassPanel" in stylesheet
    assert GLASS_BG in stylesheet
    assert GLASS_BORDER in stylesheet
    assert GLASS_HIGHLIGHT in stylesheet
    assert f"border-radius: {GLASS_RADIUS}" in stylesheet
    for surface in ("QFrame#dashboardCard", "QFrame#skillCard", "QFrame#chatToast"):
        assert surface in stylesheet


def test_nested_glass_insets_stay_transparent():
    stylesheet = build_dark_stylesheet()

    assert "QWidget#glassPanelInset" in stylesheet
    assert "QFrame#glassPanelInset" in stylesheet
    inset_block = stylesheet.split("QWidget#glassPanelInset", 1)[1].split("}", 1)[0]
    assert "background: transparent" in inset_block
    assert "border: 0" in inset_block


def test_chat_composer_and_chips_use_the_stronger_glass_tint():
    from hellsaiz_pc_ai.app.theme import GLASS_BG_STRONG

    stylesheet = build_dark_stylesheet()

    composer_block = stylesheet.rsplit("QTextEdit#chatComposer", 1)[1].split("}", 1)[0]
    assert GLASS_BG_STRONG in composer_block
    chips_block = stylesheet.rsplit("QWidget#chatQuickCommandsBody", 1)[1].split("}", 1)[0]
    assert GLASS_BG_STRONG in chips_block
    assert "border-color: rgba(255, 255, 255, 60)" in stylesheet
