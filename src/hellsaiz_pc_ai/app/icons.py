"""Lucide SVG icons rendered through QSvgRenderer with theme recolouring.

The packaged build has no guaranteed emoji font, and hand-drawn QPainter glyphs
were a stopgap. These helpers load the vendored Lucide SVGs, replace
``currentColor`` with the requested theme colour and cache one QIcon per
(name, colour) pair.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
DEFAULT_COLOR = "#F2EFEA"

_CACHE: dict[tuple[str, str], QIcon] = {}


def icon_path(name: str) -> Path:
    """Absolute path of a vendored Lucide SVG."""
    return ICON_DIR / f"{name}.svg"


class SvgIconEngine(QIconEngine):
    """Render a recoloured SVG at any size the widget asks for."""

    def __init__(self, svg: bytes) -> None:
        super().__init__()
        self._svg = svg

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        QSvgRenderer(self._svg).render(painter, QRectF(rect))

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap

    def clone(self) -> QIconEngine:
        return SvgIconEngine(self._svg)


def _recolored(name: str, color: str) -> bytes | None:
    path = icon_path(name)
    if not path.is_file():
        return None
    svg = path.read_text(encoding="utf-8")
    return svg.replace("currentColor", color).encode("utf-8")


def load_icon(name: str, color: str = DEFAULT_COLOR) -> QIcon:
    """Cached QIcon for a Lucide asset, recoloured to ``color``."""
    key = (name, color)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    svg = _recolored(name, color)
    if svg is None:
        return QIcon()
    icon = QIcon(SvgIconEngine(svg))
    _CACHE[key] = icon
    return icon


def available_icons() -> tuple[str, ...]:
    """Names of the vendored icons (used by tests and diagnostics)."""
    return tuple(sorted(path.stem for path in ICON_DIR.glob("*.svg")))
