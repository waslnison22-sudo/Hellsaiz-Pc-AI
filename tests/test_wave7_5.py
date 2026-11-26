"""Batch 5 contracts: knice main-page tokens."""

from __future__ import annotations

from hellsaiz_pc_ai.app.dashboard_texts import greeting_note
from hellsaiz_pc_ai.app.theme import (
    CARD_EDGE,
    CARD_RADIUS,
    DASHBOARD_BACKDROP,
    DASHBOARD_SURFACE,
    build_dark_stylesheet,
)


def test_dashboard_card_uses_the_knice_radius_and_edge():
    stylesheet = build_dark_stylesheet()
    block = stylesheet.rsplit("QFrame#dashboardCard {", 1)[1].split("}", 1)[0]

    assert f"border-radius: {CARD_RADIUS}" in block
    assert CARD_RADIUS == "22px"
    assert f"border-top: 1px solid {CARD_EDGE}" in block
    assert DASHBOARD_SURFACE in block


def test_dashboard_surface_and_backdrop_colours():
    stylesheet = build_dark_stylesheet()

    assert DASHBOARD_SURFACE == "#212226"
    assert DASHBOARD_BACKDROP == "#17181b"
    assert "QFrame#dashboardCard:hover" in stylesheet
    assert "#2a2b30" in stylesheet
    assert DASHBOARD_BACKDROP in stylesheet


def test_big_temperature_and_mono_numbers():
    stylesheet = build_dark_stylesheet()
    temperature = stylesheet.rsplit("QLabel#weatherTemperature {", 1)[1].split("}", 1)[0]
    value = stylesheet.rsplit("QLabel#dashboardCardValue {", 1)[1].split("}", 1)[0]
    reminders = stylesheet.rsplit("QListWidget#dashboardRemindersList {", 1)[1].split("}", 1)[0]

    assert "font-size: 46px" in temperature
    assert "font-weight: 800" in temperature
    assert "Consolas" in temperature
    assert "Consolas" in value
    assert "Consolas" in reminders


def test_lively_greeting_phrases():
    assert greeting_note(9, "") == "Работаем в спокойном темпе."
    assert greeting_note(15, "") == "День идёт — я рядом."
    assert greeting_note(20, "") == "Вечер. Сделаем тише и проще."
    assert greeting_note(2, "") == "Ночная смена. Я на связи."


def test_forecast_items_split_day_and_temperature(monkeypatch):
    from hellsaiz_pc_ai.tools import public_info

    report = public_info.WeatherReport(
        city="Ставрополь",
        latitude=45.0,
        longitude=41.9,
        temperature=6.0,
        apparent=5.0,
        humidity=61.0,
        wind=3.0,
        code=0,
        condition="Ясно",
        icon="☀️",
        hourly=(),
        daily=(
            public_info.WeatherDay("Сб", 2.0, -3.0, 0, "Ясно", "☀️"),
            public_info.WeatherDay("Пт", 4.0, -1.0, 2, "Малооблачно", "🌤"),
        ),
    )

    items = report.forecast_items()

    assert items == [("Сб", "+2°"), ("Пт", "+4°")]
    assert report.forecast_line() == "Сб +2°  Пт +4°"
