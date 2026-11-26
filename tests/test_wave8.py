"""Wave-8 contracts: knice dashboard grid, tokens and structure."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hellsaiz_pc_ai.app.theme import (
    CARD_PADDING,
    CARD_SHADOW_BLUR,
    DASHBOARD_MARGIN_SIDE,
    DASHBOARD_MARGIN_TOP,
    GRID_BREAKPOINTS,
    GRID_GAP,
    build_dark_stylesheet,
)

DASHBOARD_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "hellsaiz_pc_ai"
    / "app"
    / "dashboard_page.py"
)

try:  # PySide6 widgets are unavailable on headless Linux runners.
    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.app.dashboard_page import DashboardPage, columns_for_width

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


class _FakeReminderStore:
    def list_pending(self):
        return []


def test_grid_tokens_are_defined_and_sane():
    assert 8 <= GRID_GAP <= 20
    assert 12 <= CARD_PADDING <= 24
    assert DASHBOARD_MARGIN_TOP >= CARD_SHADOW_BLUR, "top margin must fit the card shadow"
    assert DASHBOARD_MARGIN_SIDE > 0
    assert CARD_SHADOW_BLUR >= 16
    assert [columns for _threshold, columns in GRID_BREAKPOINTS] == [1, 2, 3]


@requires_qt
def test_columns_follow_the_window_width():
    assert columns_for_width(760) == 1
    assert columns_for_width(1280) == 2
    assert columns_for_width(1920) == 3


@requires_qt
def test_dashboard_relayouts_when_width_changes():
    app = QApplication.instance() or QApplication([])
    page = DashboardPage(reminder_store=_FakeReminderStore())
    page.show()

    page.resize(800, 700)
    app.processEvents()
    assert page._columns == 1

    page.resize(1200, 700)
    app.processEvents()
    assert page._columns == 2

    page.resize(1800, 700)
    app.processEvents()
    assert page._columns == 3


def test_dashboard_has_no_hardcoded_hex_colours():
    source = DASHBOARD_SOURCE.read_text(encoding="utf-8")

    assert re.search(r"#[0-9A-Fa-f]{6}", source) is None


def test_dashboard_anti_regressions():
    source = DASHBOARD_SOURCE.read_text(encoding="utf-8")

    assert "Диагностика" not in source
    assert "mainNavigation" not in source
    assert "sidebar" not in source.lower()
    assert "Версия 0.1.9" not in source


@requires_qt
def test_dashboard_widget_contract_names():
    QApplication.instance() or QApplication([])
    page = DashboardPage(reminder_store=_FakeReminderStore())
    names = {widget.objectName() for widget in page.findChildren(object)}

    for expected in (
        "dashboardGreeting",
        "weatherTemperature",
        "remindersCount",
        "quickChip",
        "systemBarValue",
        "quickCommandInput",
        "dashboardCard",
    ):
        assert expected in names, expected


@requires_qt
def test_metrics_timer_stops_when_the_page_is_hidden():
    app = QApplication.instance() or QApplication([])
    page = DashboardPage(reminder_store=_FakeReminderStore())
    page.show()
    app.processEvents()
    assert page._metrics_timer.isActive() is True

    page.hide()
    app.processEvents()

    assert page._metrics_timer.isActive() is False


def test_knice_card_style_is_a_dashboard_token():
    stylesheet = build_dark_stylesheet()
    block = stylesheet.rsplit("QFrame#dashboardCard {", 1)[1].split("}", 1)[0]

    assert "border-radius: 22px" in block
