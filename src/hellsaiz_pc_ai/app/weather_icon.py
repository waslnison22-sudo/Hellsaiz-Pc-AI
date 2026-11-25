"""Meteocons weather icons with a light QTimer animation.

The dashboard card used emoji glyphs, which are missing from some Windows
builds. These widgets render the vendored Meteocons SVGs and add a subtle
motion: sun rays sway, clouds drift, rain and snow fall, thunderstorms flash.
Rendering failures degrade to the old emoji instead of breaking the card.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons" / "weather"
DEFAULT_SIZE = 56
FRAME_MS = 33
NIGHT_START_HOUR = 21
NIGHT_END_HOUR = 6
FALLBACK_ICON = "cloudy"
FALLBACK_TEXT = "☁️"

_DRIZZLE = ("дождь", "ливень", "морось", "гроза", "rain", "drizzle")
_STORM = ("гроза", "гром", "молния", "thunder", "storm")
_SNOW = ("снег", "снегопад", "метель", "snow")
_FOG = ("туман", "дымка", "мгла", "fog", "mist")
_CLEAR = ("ясно", "солнечно", "clear", "sun")
_PARTLY = ("малооблач", "переменная облачность", "частичн", "partly")
_CLOUDY = ("пасмурно", "облачно", "облач", "cloud", "overcast")


def is_night_hour(hour: int) -> bool:
    """Night is a coarse guess until the API exposes is_day."""
    return hour < NIGHT_END_HOUR or hour >= NIGHT_START_HOUR


def map_weather_icon(condition: str, hour: int) -> str:
    """Map a human condition string to a vendored Meteocons SVG name."""
    text = str(condition or "").casefold()
    night = is_night_hour(int(hour))
    if any(word in text for word in _STORM):
        return "thunderstorms"
    if any(word in text for word in _SNOW):
        return "snow"
    if any(word in text for word in _DRIZZLE):
        return "rain"
    if any(word in text for word in _FOG):
        return "fog"
    if any(word in text for word in _CLEAR):
        return "clear-night" if night else "clear-day"
    if any(word in text for word in _PARTLY):
        return "partly-cloudy-night" if night else "partly-cloudy-day"
    if any(word in text for word in _CLOUDY):
        return "cloudy"
    return FALLBACK_ICON


class WeatherIconWidget(QWidget):
    """56px Meteocons view with a compact, visibility-aware animation."""

    def __init__(self, parent: QWidget | None = None, size: int = DEFAULT_SIZE) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._renderer: QSvgRenderer | None = None
        self._icon_name = FALLBACK_ICON
        self._dimmed = False
        self._phase = 0.0
        self._elapsed_ms = 0
        self._flash_until = 0.0
        self._next_flash_ms = 3000
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)
        self.set_icon(FALLBACK_ICON)

    # --- state ---------------------------------------------------------
    @property
    def icon_name(self) -> str:
        return self._icon_name

    @property
    def is_animating(self) -> bool:
        return self._timer.isActive()

    def set_icon(self, name: str) -> None:
        """Load an SVG by name; a missing or broken file keeps the emoji fallback."""
        self._icon_name = name
        self._renderer = None
        path = ICON_DIR / f"{name}.svg"
        try:
            if path.is_file():
                self._renderer = QSvgRenderer(path.read_bytes())
                if not self._renderer.isValid():
                    self._renderer = None
        except (OSError, ValueError):
            self._renderer = None
        self._sync_timer()
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        """Grey the icon out for error states without stopping the animation."""
        self._dimmed = bool(dimmed)
        self.update()

    # --- animation -----------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().hideEvent(event)
        self._sync_timer()

    def _is_visible_now(self) -> bool:
        parent = self.parentWidget()
        return self.isVisibleTo(parent) if parent is not None else self.isVisible()

    def _sync_timer(self) -> None:
        if not self._is_visible_now() or self._renderer is None:
            self._timer.stop()
            return
        if not self._timer.isActive():
            self._timer.start()

    def _tick(self) -> None:
        if not self._is_visible_now():
            self._timer.stop()
            return
        self._elapsed_ms += FRAME_MS
        self._phase = (self._elapsed_ms / 1000.0) % 4.0
        if self._icon_name == "thunderstorms":
            if self._elapsed_ms >= self._next_flash_ms:
                self._flash_until = self._elapsed_ms + 140
                self._next_flash_ms = self._elapsed_ms + 3200 + (self._elapsed_ms % 900)
        self.update()

    # --- painting ------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, self.width(), self.height())
        if self._renderer is None:
            painter.setPen(QColor("#A6A29C" if self._dimmed else "#F2EFEA"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, FALLBACK_TEXT)
            painter.end()
            return

        painter.save()
        if self._dimmed:
            painter.setOpacity(0.45)
        name = self._icon_name
        if name.startswith(("clear", "partly")):
            angle = math.sin(self._phase * math.pi / 2) * 3.0
            painter.translate(rect.center())
            painter.rotate(angle)
            painter.translate(-rect.center())
            self._renderer.render(painter, rect)
        elif "cloudy" in name:
            offset = math.sin(self._phase * math.pi / 2) * 4.0
            painter.translate(offset, 0)
            self._renderer.render(painter, rect)
        else:
            self._renderer.render(painter, rect)

        if name in {"rain", "thunderstorms"}:
            self._paint_rain(painter, rect)
        elif name == "snow":
            self._paint_snow(painter, rect)
        painter.restore()

        if name == "thunderstorms" and self._elapsed_ms < self._flash_until:
            painter.fillRect(rect, QColor(255, 255, 255, 70))
        painter.end()

    def _paint_rain(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor(120, 170, 255, 190), 1.6))
        for index in range(3):
            cycle = (self._phase + index * 0.33) % 1.0
            x = rect.left() + rect.width() * (0.34 + index * 0.14)
            y = rect.top() + rect.height() * (0.34 + cycle * 0.42)
            painter.drawLine(QPointF(x, y), QPointF(x - 1.5, y + 5.0))

    def _paint_snow(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(235, 240, 255, 200))
        for index in range(3):
            cycle = (self._phase + index * 0.33) % 1.0
            x = rect.left() + rect.width() * (0.34 + index * 0.14)
            y = rect.top() + rect.height() * (0.30 + cycle * 0.46)
            painter.drawEllipse(QPointF(x, y), 1.5, 1.5)
