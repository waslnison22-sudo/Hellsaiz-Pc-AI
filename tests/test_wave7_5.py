"""Batch 5 contracts: knice main-page hub."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hellsaiz_pc_ai.app.dashboard_texts import (
    greeting_note,
    last_reply_empty_note,
    reminders_count_label,
    system_comment,
)
from hellsaiz_pc_ai.app.theme import (
    CARD_RADIUS,
    DASHBOARD_BACKDROP,
    DASHBOARD_HOVER,
    DASHBOARD_SURFACE,
    build_dark_stylesheet,
)

try:  # The widget module imports PySide6 — unavailable on headless Linux runners.
    from hellsaiz_pc_ai.app import dashboard_page as dashboard_module
except ImportError:  # pragma: no cover - runner-specific
    dashboard_module = None

requires_dashboard_module = pytest.mark.skipif(
    dashboard_module is None,
    reason="PySide6-backed dashboard module is not available on this runner",
)


@requires_dashboard_module
def test_dashboard_card_uses_the_knice_radius_and_edge():
    """Wave 8 paints the surface and the soft shadow inside the card widget.

    The stylesheet keeps only the radius; the shadow, surface colour and the
    inset top highlight moved into _ShadowCard.paintEvent, so the contract now
    reads the tokens plus the radius from the stylesheet.
    """
    stylesheet = build_dark_stylesheet()
    block = stylesheet.rsplit("QFrame#dashboardCard {", 1)[1].split("}", 1)[0]
    source = Path(dashboard_module.__file__).read_text(encoding="utf-8")

    assert f"border-radius: {CARD_RADIUS}" in block
    assert CARD_RADIUS == "22px"
    assert "QColor(33, 34, 38)" in source
    assert "QColor(255, 255, 255, 18)" in source
    assert DASHBOARD_SURFACE == "#212226"


def test_dashboard_surface_and_backdrop_colours():
    stylesheet = build_dark_stylesheet()

    assert DASHBOARD_SURFACE == "#212226"
    assert DASHBOARD_BACKDROP == "#17181b"
    assert DASHBOARD_HOVER == "#2a2b30"
    assert DASHBOARD_BACKDROP in stylesheet


def test_big_temperature_and_mono_numbers():
    stylesheet = build_dark_stylesheet()
    temperature = stylesheet.rsplit("QLabel#weatherTemperature {", 1)[1].split("}", 1)[0]

    assert "font-size: 34px" in temperature
    assert "font-weight: 800" in temperature
    assert "Consolas" in temperature
    assert "Consolas" in stylesheet.rsplit("QLabel#dashboardCardValue {", 1)[1].split("}", 1)[0]


def test_lively_greeting_phrases():
    assert greeting_note(9, "") == "Работаем в спокойном темпе."
    assert greeting_note(15, "") == "День идёт — я рядом."
    assert greeting_note(20, "") == "Сделаем тише и проще — день закончился."
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
        fetched_at=datetime.now(timezone.utc),
        daily=(
            public_info.WeatherDay("Сб", 2.0, -3.0, 0, "Ясно", "☀️"),
            public_info.WeatherDay("Пт", 4.0, -1.0, 2, "Малооблачно", "🌤"),
        ),
    )

    items = report.forecast_items()

    assert items == [("Сб", "+2°"), ("Пт", "+4°")]
    assert report.forecast_line() == "Сб +2°  Пт +4°"


@requires_dashboard_module
def test_dashboard_dropped_the_ballast():
    source = inspect.getsource(dashboard_module)
    assert "Всё локально" not in source
    assert "Применить" not in source
    assert "Версия " not in source


def test_reminders_count_label_plural():
    assert reminders_count_label(0) == "На сегодня ничего нет"
    assert reminders_count_label(1) == "1 напоминание на сегодня"
    assert reminders_count_label(2) == "2 напоминания на сегодня"
    assert reminders_count_label(5) == "5 напоминаний на сегодня"
    assert reminders_count_label(12) == "12 напоминаний на сегодня"
    assert reminders_count_label(21) == "21 напоминание на сегодня"


def test_system_comment_thresholds():
    assert system_comment(None) == "Метрики пока не считаны."
    assert system_comment(12) == "Работаем в спокойном темпе."
    assert system_comment(39.9) == "Работаем в спокойном темпе."
    assert system_comment(40) == "Средняя нагрузка — всё под контролем."
    assert system_comment(79) == "Средняя нагрузка — всё под контролем."
    assert system_comment(85) == "Процессор сейчас трудится вовсю."


@requires_dashboard_module
def test_dashboard_hub_structure():
    source = inspect.getsource(dashboard_module)
    for needle in (
        "Музыка",
        "Быстрые команды",
        "Система",
        "Последний ответ",
        "музыка назад",
        "музыка пауза",
        "музыка дальше",
        "on_open_chat",
        "set_last_reply",
        "system_snapshot",
    ):
        assert needle in source, needle


@requires_dashboard_module
def test_media_icons_are_vendored():
    package_root = (
        Path(dashboard_module.__file__).resolve().parents[1] / "assets" / "icons"
    )
    for name in ("skip-back.svg", "skip-forward.svg", "play.svg", "pause.svg"):
        assert (package_root / name).exists(), name


def test_system_bar_uses_progress_styling():
    stylesheet = build_dark_stylesheet()
    block = stylesheet.rsplit("QProgressBar#systemBar {", 1)[1].split("}", 1)[0]

    assert "border-radius: 3px" in block
    assert "max-height: 6px" in block
    assert "QProgressBar#systemBar::chunk" in stylesheet
    assert "#E8C29E" in stylesheet.rsplit("QProgressBar#systemBar::chunk {", 1)[1].split("}", 1)[0]


def test_last_reply_empty_note_text():
    assert last_reply_empty_note() == "Пока тишина. Спроси меня о чём угодно."


def test_greeting_note_respects_persona():
    assert "сэр" in greeting_note(14, "джарвис")
    note = greeting_note(14, "хеллсайз")
    assert "сэр" not in note.casefold()
    assert note
