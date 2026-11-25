"""Vector icons for chat controls, now backed by vendored Lucide SVGs.

Historically these were painted with QPainter because packaged Windows builds
can lack an emoji font. They now delegate to :mod:`hellsaiz_pc_ai.app.icons`,
which renders Lucide sources through QSvgRenderer and recolours them to the
astra palette. The function names are kept for existing call sites.
"""

from __future__ import annotations

from PySide6.QtGui import QIcon

from hellsaiz_pc_ai.app.icons import load_icon

_LIGHT = "#F2EFEA"
_MUTED = "#A6A29C"
_DARK = "#1A140F"


def mic_icon() -> QIcon:
    """Microphone glyph for the voice-input button."""
    return load_icon("mic", _LIGHT)


def send_icon() -> QIcon:
    """Send arrow (dark on the amber gradient)."""
    return load_icon("send", _DARK)


def refresh_icon() -> QIcon:
    """Refresh arrow for card headers."""
    return load_icon("refresh-cw", _MUTED)


def trash_icon() -> QIcon:
    """Trash can for destructive buttons."""
    return load_icon("trash-2", _MUTED)


def mic_off_icon() -> QIcon:
    """Muted microphone used by the barge-in control."""
    return load_icon("mic-off", _MUTED)


def sparkles_icon(color: str = _MUTED) -> QIcon:
    """Sparkles for assistant-branded labels."""
    return load_icon("sparkles", color)


def nav_icon(name: str) -> QIcon:
    """Muted icon for a top-bar pill."""
    return load_icon(name, _MUTED)
