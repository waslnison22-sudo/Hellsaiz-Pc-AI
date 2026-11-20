"""Vector icons drawn with QPainter.

Packaged Windows builds can lack a complete emoji font, so glyph-based button
labels (mic, send, refresh, trash) render as empty boxes or tofu glyphs.
These helpers paint the same symbols as vector shapes, keeping the controls
independent from font coverage.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_LIGHT = "#F2EFEA"
_MUTED = "#A6A29C"
_DARK = "#1A140F"


def _pack(draw) -> QIcon:
    """Render the drawing callback at 1x and 2x and pack both into one QIcon."""
    icon = QIcon()
    for ratio in (1.0, 2.0):
        size = int(20 * ratio)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.scale(ratio, ratio)
        draw(painter)
        painter.end()
        pixmap.setDevicePixelRatio(ratio)
        icon.addPixmap(pixmap)
    return icon


def _pen(color: str, width: float) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def mic_icon() -> QIcon:
    """Microphone glyph for the voice-input button."""

    def draw(painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_LIGHT))
        painter.drawRoundedRect(QRectF(7.2, 2.6, 5.6, 8.8), 2.8, 2.8)
        painter.setPen(_pen(_LIGHT, 1.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(4.2, 4.2, 11.6, 11.6), 180 * 16, 180 * 16)
        painter.drawLine(QPointF(10.0, 15.8), QPointF(10.0, 17.2))
        painter.drawLine(QPointF(7.3, 17.2), QPointF(12.7, 17.2))

    return _pack(draw)


def send_icon() -> QIcon:
    """Right arrow for the send button (dark on the amber gradient)."""

    def draw(painter: QPainter) -> None:
        painter.setPen(_pen(_DARK, 2.2))
        painter.drawLine(QPointF(3.8, 10.0), QPointF(11.6, 10.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_DARK))
        head = QPainterPath()
        head.moveTo(10.4, 6.0)
        head.lineTo(16.4, 10.0)
        head.lineTo(10.4, 14.0)
        head.closeSubpath()
        painter.drawPath(head)

    return _pack(draw)


def refresh_icon() -> QIcon:
    """Circular arrow for card refresh buttons (muted grey like the old glyph)."""

    def draw(painter: QPainter) -> None:
        painter.setPen(_pen(_MUTED, 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(4.0, 4.0, 12.0, 12.0), 40 * 16, 290 * 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_MUTED))
        head = QPainterPath()
        head.moveTo(11.2, 1.6)
        head.lineTo(15.8, 4.6)
        head.lineTo(11.6, 7.8)
        head.closeSubpath()
        painter.drawPath(head)

    return _pack(draw)


def trash_icon() -> QIcon:
    """Trash can for the clear-chat button (muted grey like the old glyph)."""

    def draw(painter: QPainter) -> None:
        painter.setPen(_pen(_MUTED, 1.8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(8.2, 3.0, 3.6, 2.6), 1.0, 1.0)
        painter.drawLine(QPointF(4.6, 5.6), QPointF(15.4, 5.6))
        body = QPainterPath()
        body.moveTo(6.2, 5.6)
        body.lineTo(6.9, 16.6)
        body.quadTo(6.95, 17.4, 7.7, 17.4)
        body.lineTo(12.3, 17.4)
        body.quadTo(13.05, 17.4, 13.1, 16.6)
        body.lineTo(13.8, 5.6)
        painter.drawPath(body)
        painter.drawLine(QPointF(8.8, 8.4), QPointF(9.1, 15.0))
        painter.drawLine(QPointF(11.2, 8.4), QPointF(10.9, 15.0))

    return _pack(draw)
