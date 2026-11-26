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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from hellsaiz_pc_ai.app.chat_page import GradientBrandLabel
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


@requires_qt
def test_weather_condition_never_overlaps_the_temperature():
    """Layout contract: the caption is beside the number, not stacked on it."""
    app = QApplication.instance() or QApplication([])
    page = DashboardPage(reminder_store=_FakeReminderStore())
    page.resize(1240, 820)
    page.show()
    app.processEvents()
    # Headless runners do not always activate the nested layouts on show().
    page.layout().activate()
    page._relayout_grid(page.width(), force=True)
    page.layout().activate()
    app.processEvents()

    labels = page.findChildren(QWidget)
    temperature = next(w for w in labels if w.objectName() == "weatherTemperature")
    condition = next(w for w in labels if w.objectName() == "weatherCondition")
    for widget in (temperature, condition):
        widget.parent().layout().activate()
    app.processEvents()

    temperature_rect = temperature.geometry()
    condition_rect = condition.geometry()

    assert temperature_rect.height() > 0 and condition_rect.height() > 0
    # Siblings in a horizontal row: their rectangles share the row, not pixels.
    assert not temperature_rect.intersects(condition_rect), (
        temperature_rect.getRect(),
        condition_rect.getRect(),
    )


def test_knice_card_style_is_a_dashboard_token():
    stylesheet = build_dark_stylesheet()
    block = stylesheet.rsplit("QFrame#dashboardCard {", 1)[1].split("}", 1)[0]

    assert "border-radius: 22px" in block


@requires_qt
def test_greeting_is_left_aligned():
    QApplication.instance() or QApplication([])
    page = DashboardPage(reminder_store=_FakeReminderStore())

    brands = [w for w in page.findChildren(QWidget) if isinstance(w, GradientBrandLabel)]

    assert brands, "the dashboard greeting must use the gradient brand label"
    for brand in brands:
        assert bool(brand._align & Qt.AlignmentFlag.AlignLeft)
        assert not bool(brand._align & Qt.AlignmentFlag.AlignHCenter)
