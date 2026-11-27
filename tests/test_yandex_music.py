"""Yandex Music card contracts: window-title parsing and the no-player state."""

from __future__ import annotations

import pytest

from hellsaiz_pc_ai.app.yandex_music import NowPlaying, parse_window_title

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


def test_title_with_em_dash_splits_artist_and_track():
    playing = parse_window_title("Radiohead — Creep")

    assert playing.artist == "Radiohead"
    assert playing.track == "Creep"
    assert playing.display_line() == "Radiohead — Creep"


def test_title_with_hyphen_splits_artist_and_track():
    playing = parse_window_title("Radiohead - Creep")

    assert playing.artist == "Radiohead"
    assert playing.track == "Creep"


def test_app_name_alone_means_no_track():
    playing = parse_window_title("Яндекс Музыка")

    assert playing.has_track is False


def test_empty_title_is_safe():
    assert parse_window_title("") == NowPlaying(title="")


@requires_qt
def test_player_card_shows_the_no_player_state(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "hellsaiz_pc_ai.app.dashboard_page.now_playing", lambda: NowPlaying(title="")
    )
    page = DashboardPage(reminder_store=_FakeReminderStore())

    page._refresh_now_playing()

    assert page._media_track.text() == "Яндекс Музыка не запущена"
    assert page._media_play_button.isEnabled() is False


@requires_qt
def test_player_card_shows_a_running_track(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(
        "hellsaiz_pc_ai.app.dashboard_page.now_playing",
        lambda: NowPlaying(title="Radiohead — Creep", artist="Radiohead", track="Creep"),
    )
    page = DashboardPage(reminder_store=_FakeReminderStore())

    page._refresh_now_playing()

    assert page._media_track.text() == "Radiohead — Creep"
    assert page._media_next_button.isEnabled() is True
