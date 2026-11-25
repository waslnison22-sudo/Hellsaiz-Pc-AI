import pytest

try:
    from hellsaiz_pc_ai.app import hud_components
    from hellsaiz_pc_ai.app.theme import build_dark_stylesheet
except ImportError as exc:  # Linux CI runners lack Qt native libs (libEGL); full run on Windows.
    pytest.skip(f"Qt native libraries unavailable: {exc}", allow_module_level=True)


def test_hud_module_exposes_expected_widgets():
    for name in ("SectionCard", "ToggleSwitch", "StatChip", "EmptyState", "PageFader", "fade_in"):
        assert hasattr(hud_components, name), name


def test_stat_chip_levels_have_themed_styles():
    stylesheet = build_dark_stylesheet()
    for level in ("Ok", "Warn", "Err"):
        assert f"QLabel#statChip{level}" in stylesheet, level


def test_theme_styles_new_wave3_components():
    stylesheet = build_dark_stylesheet()

    assert "QFrame#skillCard" in stylesheet
    assert "QLabel#skillCardTitle" in stylesheet
    assert "QLabel#privacyNote" in stylesheet
    assert "QFrame#emptyState" in stylesheet
    assert "QTabBar::tab:!selected" in stylesheet


def test_theme_keeps_existing_contract():
    stylesheet = build_dark_stylesheet()

    assert "min-height: 36px" in stylesheet
    assert "QTabBar::tab:selected" in stylesheet
    assert "QFrame#dashboardCard" in stylesheet
    assert "QLabel#dashboardCardValue" in stylesheet
    assert "QPushButton:focus" in stylesheet
    assert "QLineEdit:focus" in stylesheet
