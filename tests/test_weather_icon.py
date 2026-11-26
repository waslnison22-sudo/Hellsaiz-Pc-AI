"""Tests for the Meteocons weather icons and their mapping."""

from __future__ import annotations

import pytest

try:  # PySide6 GUI libraries are absent on headless Linux runners.
    from hellsaiz_pc_ai.app.weather_icon import is_night_hour, map_weather_icon

    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.app.weather_icon import WeatherIconWidget

    _QT_AVAILABLE = True
except ImportError as exc:  # pragma: no cover - runner-specific
    pytest.skip(f"Qt native libraries unavailable: {exc}", allow_module_level=True)

_requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


@pytest.mark.parametrize(
    ("condition", "hour", "expected"),
    [
        ("Ясно", 12, "clear-day"),
        ("Солнечно", 9, "clear-day"),
        ("Ясно", 23, "clear-night"),
        ("Ясно", 5, "clear-night"),
        ("Малооблачно", 12, "partly-cloudy-day"),
        ("Переменная облачность", 22, "partly-cloudy-night"),
        ("Пасмурно", 12, "cloudy"),
        ("Облачно", 3, "cloudy"),
        ("Небольшой дождь", 12, "rain"),
        ("Ливень", 4, "rain"),
        ("Снегопад", 12, "snow"),
        ("Гроза", 13, "thunderstorms"),
        ("Туман", 7, "fog"),
        ("Дымка", 7, "fog"),
        ("странная погода", 12, "cloudy"),
    ],
)
def test_map_weather_icon(condition, hour, expected):
    assert map_weather_icon(condition, hour) == expected


def test_night_hours_are_coarse():
    assert is_night_hour(5) is True
    assert is_night_hour(6) is False
    assert is_night_hour(20) is False
    assert is_night_hour(21) is True


@_requires_qt
def test_widget_does_not_animate_while_hidden():
    app = QApplication.instance() or QApplication([])
    widget = WeatherIconWidget()
    widget.set_icon("rain")

    assert widget.is_animating is False
    widget.show()
    app.processEvents()
    assert widget.is_animating is True
    widget.hide()
    app.processEvents()
    assert widget.is_animating is False


@_requires_qt
def test_unknown_icon_falls_back_without_raising():
    QApplication.instance() or QApplication([])
    widget = WeatherIconWidget()

    widget.set_icon("no-such-weather")

    assert widget.icon_name == "no-such-weather"
    assert widget.grab().isNull() is False
