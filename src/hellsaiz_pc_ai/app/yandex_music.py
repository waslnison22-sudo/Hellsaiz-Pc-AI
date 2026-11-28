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
BROWSER_NOISE = (
    "слушать онлайн",
    "на яндекс музыке",
    "бесплатно",
    "хорошем качестве",
)


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
    lowered_raw = raw.casefold()
    if any(noise in lowered_raw for noise in BROWSER_NOISE):
        return NowPlaying(title="", window_title=raw)

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


PROCESS_MARKERS = ("музык", "yandexmusic", "yandex music", "yandex.music")


def _process_image(pid: int) -> str:
    """Full executable path of a pid (Windows only), best effort."""
    if os.name != "nt":
        return ""
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            size = ctypes.c_ulong(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value
            return ""
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError):  # pragma: no cover - defensive
        return ""


def _window_owner_pid(hwnd: int) -> int:
    pid = ctypes.c_ulong(0)
    try:
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    except (AttributeError, OSError):  # pragma: no cover - defensive
        return 0
    return int(pid.value)


def player_window() -> tuple[int, str] | None:
    """The Yandex Music window handle and title, if the app is running.

    The desktop app is an Electron bundle: the process image is the Cyrillic
    «Яндекс Музыка.exe», and the window title is the current track.
    """
    candidates: list[tuple[int, str]] = []
    for hwnd, title in _window_titles():
        image = _process_image(_window_owner_pid(hwnd)).casefold()
        if image and any(marker in image for marker in PROCESS_MARKERS):
            candidates.append((hwnd, title))
    # Browser tabs about Yandex Music carry page titles, not tracks: only the
    # desktop app process counts.
    for hwnd, title in candidates:
        if title.strip():
            return hwnd, title
    return candidates[0] if candidates else None


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


def player_executable() -> str | None:
    """Path to the desktop app: known install locations, newest first."""
    if os.name != "nt":
        return None
    local = os.environ.get("LOCALAPPDATA") or ""
    roaming = os.environ.get("APPDATA") or ""
    program_files = os.environ.get("ProgramFiles") or ""
    program_files_x86 = os.environ.get("ProgramFiles(x86)") or ""
    folders = [
        os.path.join(local, "Programs", "YandexMusic"),
        os.path.join(local, "YandexMusic"),
        os.path.join(roaming, "YandexMusic"),
        os.path.join(program_files, "YandexMusic"),
        os.path.join(program_files_x86, "YandexMusic"),
    ]
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        # The bundle ships «Яндекс Музыка.exe»; ignore the uninstaller.
        candidates = [
            entry
            for entry in sorted(os.listdir(folder))
            if entry.casefold().endswith(".exe") and "uninstall" not in entry.casefold()
        ]
        for entry in candidates:
            path = os.path.join(folder, entry)
            if os.path.isfile(path):
                return path
    return None


def open_or_focus_player() -> str:
    """Focus a running player, or launch it; returns a short status word."""
    if focus_player():
        return "focused"
    executable = player_executable()
    if executable is None:
        return "missing"
    try:
        import subprocess

        subprocess.Popen([executable], close_fds=True)
    except OSError:
        logging.debug("Launching Yandex Music failed", exc_info=True)
        return "missing"
    return "launched"


# ---------------------------------------------------------------- media session


@dataclass(frozen=True)
class MediaSession:
    """What the system media transport controls report for a player."""

    app: str
    title: str
    artist: str
    album: str
    status: str
    artwork: bytes = b""
    position_seconds: float = 0.0
    duration_seconds: float = 0.0

    @property
    def has_track(self) -> bool:
        return bool(self.title.strip())

    def display_line(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} — {self.title}"
        return self.title


PLAYBACK_STATES = {
    1: "закрыто",
    2: "открыто",
    3: "меняется",
    4: "пауза",
    5: "играет",
    6: "стоп",
}


def playback_state_name(raw: object) -> str:
    """Map a MediaPlaybackStatus value to a Russian label."""
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "неизвестно"
    return PLAYBACK_STATES.get(value, "неизвестно")


def _session_snapshot() -> MediaSession | None:
    """Read the current session synchronously; None when winrt is missing."""
    try:
        import asyncio

        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )
    except ImportError:
        return None

    async def read() -> MediaSession | None:
        manager = await Manager.request_async()
        session = manager.get_current_session()
        if session is None:
            return None
        app = str(session.source_app_user_model_id or "")
        if "yandex" not in app.casefold():
            return None
        info = await session.try_get_media_properties_async()
        status = playback_state_name(session.get_playback_info().playback_status)
        position_seconds = 0.0
        duration_seconds = 0.0
        try:
            timeline = session.get_timeline_properties()
            position_seconds = float(timeline.position.total_seconds())
            duration_seconds = float(timeline.end_time.total_seconds())
            if duration_seconds <= 0:
                duration_seconds = float(timeline.max_seek_time.total_seconds())
            if duration_seconds <= 0:
                duration_seconds = float(
                    getattr(timeline, "min_seek_time", timeline.position).total_seconds()
                )
        except Exception:  # noqa: BLE001 - timeline is optional
            logging.debug("Timeline read failed", exc_info=True)
        artwork = b""
        thumbnail = getattr(info, "thumbnail", None)
        if thumbnail is not None:
            try:
                from winrt.windows.storage.streams import DataReader

                stream = await thumbnail.open_read_async()
                size = int(stream.size)
                if 0 < size <= 8 * 1024 * 1024:
                    reader = DataReader(stream)
                    await reader.load_async(size)
                    buffer = bytearray(size)
                    reader.read_bytes(buffer)
                    artwork = bytes(buffer)
            except Exception:  # noqa: BLE001 - artwork is a nice-to-have
                logging.debug("Artwork read failed", exc_info=True)
        return MediaSession(
            app=app,
            title=str(info.title or ""),
            artist=str(info.artist or ""),
            album=str(info.album_title or ""),
            status=status,
            artwork=artwork,
            position_seconds=max(0.0, position_seconds),
            duration_seconds=max(0.0, duration_seconds),
        )

    try:
        return asyncio.run(read())
    except Exception:  # noqa: BLE001 - COM/WinRT failures must not break the card
        logging.debug("Media session read failed", exc_info=True)
        return None


def media_session() -> MediaSession | None:
    """Current Yandex Music media session, if the system exposes one."""
    if os.name != "nt":
        return None
    return _session_snapshot()
