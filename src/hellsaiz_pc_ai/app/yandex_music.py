"""Yandex Music desktop integration for the dashboard player card.

The card shows what the desktop app is playing. Yandex Music exposes the current
track only through its window title, so that is the source; the playback controls
use the system media keys (the app reacts to them), and the card can bring the
player window to the front.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

YANDEX_MUSIC_TITLES = ("яндекс музыка", "yandex music", "yandex.music")
PLAYER_SUFFIXES = ("—", " - ", "|")


@dataclass(frozen=True)
class NowPlaying:
    """What the Yandex Music window reports."""

    title: str
    artist: str = ""
    track: str = ""
    window_title: str = ""

    @property
    def has_track(self) -> bool:
        """True only when a real track is known (the app title alone is not one)."""
        return bool(self.track)

    def display_line(self) -> str:
        if self.artist and self.track:
            return f"{self.artist} — {self.track}"
        return self.track or self.title


def parse_window_title(window_title: str) -> NowPlaying:
    """Turn a player window title into artist/track, tolerating many formats."""
    raw = " ".join(str(window_title or "").split())
    if not raw:
        return NowPlaying(title="")

    candidates = [raw]
    for separator in PLAYER_SUFFIXES:
        if separator in raw:
            candidates.extend(part.strip() for part in raw.split(separator))

    cleaned: list[str] = []
    for candidate in candidates:
        text = candidate.strip(" -—|·")
        lowered = text.casefold()
        if not text:
            continue
        if any(marker == lowered for marker in YANDEX_MUSIC_TITLES):
            continue
        if any(marker in lowered for marker in YANDEX_MUSIC_TITLES) and len(text) < 24:
            continue
        cleaned.append(text)

    if not cleaned:
        return NowPlaying(title=raw, window_title=raw)

    primary = cleaned[0]
    if " - " in primary and primary.count(" - ") == 1:
        artist, track = (part.strip() for part in primary.split(" - ", 1))
        return NowPlaying(
            title=primary, artist=artist, track=track, window_title=raw
        )
    if "—" in primary:
        artist, track = (part.strip() for part in primary.split("—", 1))
        if artist and track:
            return NowPlaying(
                title=primary, artist=artist, track=track, window_title=raw
            )
    return NowPlaying(title=primary, track=primary, window_title=raw)


def _window_titles() -> list[tuple[int, str]]:
    """Visible top-level window titles (Windows only, empty elsewhere)."""
    if os.name != "nt":
        return []
    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError):  # pragma: no cover - non-Windows
        return []

    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd: Any, _lparam: Any) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        found.append((int(hwnd), buffer.value))
        return True

    try:
        user32.EnumWindows(callback, 0)
    except OSError:  # pragma: no cover - defensive
        logging.debug("EnumWindows failed", exc_info=True)
        return []
    return found


def player_window() -> tuple[int, str] | None:
    """The Yandex Music window handle and title, if the app is running."""
    for hwnd, title in _window_titles():
        lowered = title.casefold()
        if any(marker in lowered for marker in YANDEX_MUSIC_TITLES) or " - " in title:
            if "—" in title or "-" in title:
                return hwnd, title
    return None


def now_playing() -> NowPlaying:
    """Current track as reported by the Yandex Music window."""
    window = player_window()
    if window is None:
        return NowPlaying(title="")
    return parse_window_title(window[1])


def focus_player() -> bool:
    """Bring the Yandex Music window to the front; False when it is not running."""
    window = player_window()
    if window is None:
        return False
    if sys.platform != "win32":  # pragma: no cover - non-Windows
        return False
    hwnd = window[0]
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        return True
    except OSError:  # pragma: no cover - defensive
        logging.debug("Focusing Yandex Music failed", exc_info=True)
        return False
