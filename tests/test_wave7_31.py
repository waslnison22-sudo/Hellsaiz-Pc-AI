"""Wave-7 3.1 contracts: skill cards (item 1)."""

from __future__ import annotations

import pytest

from hellsaiz_pc_ai.app.theme import GLASS_RADIUS, build_dark_stylesheet

try:  # PySide6 GUI libraries are absent on headless Linux runners.
    from PySide6.QtWidgets import QApplication

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

_requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


def test_skill_cards_use_the_glass_radius():
    stylesheet = build_dark_stylesheet()
    block = stylesheet.split("QFrame#skillCard", 1)[1].split("}", 1)[0]

    assert f"border-radius: {GLASS_RADIUS}" in block


@_requires_qt
def test_skill_card_gets_hover_feedback():
    QApplication.instance() or QApplication([])
    from hellsaiz_pc_ai.app.skills_page import _skill_card

    card = _skill_card("🚀", "Программы", "Запуск приложений")

    assert card.property("fxInstalled") is True


def test_error_notice_style_is_amber():
    stylesheet = build_dark_stylesheet()
    block = stylesheet.split("QFrame#errorNotice", 1)[1].split("}", 1)[0]

    assert "232, 194, 158" in block
    text_block = stylesheet.split("QLabel#errorNoticeText", 1)[1].split("}", 1)[0]
    assert "#E8C29E" in text_block


def test_voices_page_contract_in_source():
    import inspect

    from hellsaiz_pc_ai.app import desktop

    source = inspect.getsource(desktop.main)

    assert "addWidget(installed_voices_list, 1)" in source
    assert 'load_icon("volume-2"' in source
    assert 'load_icon("circle-check"' in source
    assert 'load_icon("circle-alert"' in source
    assert "voices_error_notice" in source
    assert "errorNoticeText" in source


def test_vosk_model_path_label_is_elided_with_a_tooltip():
    import inspect

    from hellsaiz_pc_ai.app import desktop
    from hellsaiz_pc_ai.app.theme import build_dark_stylesheet

    source = inspect.getsource(desktop.main)

    assert "vosk_model_path_label" in source
    assert "elidedText" in source
    assert "Qt.TextElideMode.ElideMiddle" in source
    assert "vosk_model_path_label.setToolTip(full_path)" in source
    assert "QLabel#pathLabel" in build_dark_stylesheet()
