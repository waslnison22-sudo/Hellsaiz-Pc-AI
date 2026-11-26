"""Wave-9C contracts: scenarios gating/CTA and the offline weather cache."""

from __future__ import annotations

from pathlib import Path

import pytest

from hellsaiz_pc_ai.app import weather_cache

try:  # PySide6 widgets are unavailable on headless Linux runners.
    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.app.dashboard_page import DashboardPage

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


class _FakeReminderStore:
    def list_pending(self):
        return []


# ------------------------------------------------------------------ cache contracts


def test_weather_cache_roundtrip(tmp_path, monkeypatch):
    cache_file = tmp_path / "weather_last.json"
    monkeypatch.setattr(weather_cache, "weather_cache_path", lambda: cache_file)

    weather_cache.save_weather_cache(
        {"city": "Ставрополь", "temperature": "+1°", "condition": "Переменная облачность"}
    )

    assert cache_file.is_file()
    payload = weather_cache.load_weather_cache()
    assert payload is not None
    assert payload["temperature"] == "+1°"
    assert payload["condition"] == "Переменная облачность"
    assert payload["updated_at"]


def test_weather_cache_reports_nothing_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        weather_cache, "weather_cache_path", lambda: tmp_path / "absent.json"
    )

    assert weather_cache.load_weather_cache() is None


def test_weather_cache_lives_outside_the_temp_directory(monkeypatch):
    from hellsaiz_pc_ai.config import user_data_dir

    path = weather_cache.weather_cache_path()

    assert path.parent == user_data_dir()
    assert "temp" not in str(path).casefold()


def test_updated_label_formats_the_clock_time():
    assert weather_cache.updated_label({"updated_at": "2026-11-26T23:41:07"}) == (
        "Обновлено 23:41"
    )
    assert weather_cache.updated_label({"updated_at": "broken"}) == "Обновлено ранее"


# ------------------------------------------------------------------ dashboard offline


@requires_qt
def test_dashboard_shows_cached_weather_when_offline(monkeypatch):
    QApplication.instance() or QApplication([])
    payload = {
        "condition": "Переменная облачность",
        "temperature": "+1°",
        "details": "ветер 16 км/ч",
        "updated_at": "2026-11-26T22:05:00",
    }
    monkeypatch.setattr(
        "hellsaiz_pc_ai.app.dashboard_page.load_weather_cache", lambda: payload
    )
    page = DashboardPage(reminder_store=_FakeReminderStore())

    page._apply_cached_weather()

    assert page._weather_temperature.text() == "+1°"
    assert page._weather_condition.text() == "Переменная облачность"
    assert page._weather_note.text() == "Нет соединения — показаны сохранённые данные"
    assert page._weather_updated.text() == "Обновлено 22:05"


@requires_qt
def test_dashboard_offline_without_cache_is_human(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "hellsaiz_pc_ai.app.dashboard_page.load_weather_cache", lambda: None
    )
    page = DashboardPage(reminder_store=_FakeReminderStore())

    page._apply_cached_weather()

    assert page._weather_temperature.text() == "—"
    assert page._weather_note.text() == "Погода появится, когда появится сеть."
    assert page._weather_updated.text() == ""


