"""Built-in painter sprite renderer for the desktop companion.

Phase 1 of the companion plan (see docs/COMPANION_ARCHITECTURE.md and
sources/companion_trends_2026.md): a license-clean, programmatically drawn
character — no external art, no proprietary SDK. The renderer owns no assistant
logic: it only paints whatever snapshot the controller hands it.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from hellsaiz_pc_ai.companion.contracts import CompanionMode, CompanionSnapshot

# Palette mirrors the knice theme: warm accent on a dark body.
BODY_COLOR = QColor("#2A2B30")
BODY_EDGE = QColor("#E8C29E")
GLOW_COLOR = QColor(232, 194, 158)
ERROR_COLOR = QColor(255, 123, 114)
SLEEP_COLOR = QColor(154, 148, 138)
BUBBLE_BG = QColor(23, 23, 22, 235)
BUBBLE_TEXT = QColor("#F2EFEA")

BASE_SIZE = 128


class PainterSpriteRenderer:
    """Draws the built-in companion from a snapshot; pure painting, no logic."""

    def __init__(self) -> None:
        self._eye_phase = 0.0
        self._last_paint: float | None = None

    # -- CompanionRenderer contract ------------------------------------------

    def load_model(self, model_directory: str, entrypoint: str) -> None:
        """The built-in renderer needs no model files; kept for the contract."""
        return None

    def apply_snapshot(self, snapshot: CompanionSnapshot) -> None:
        # State arrives through paint(snapshot); nothing to cache here.
        return None

    def render_status(self) -> dict[str, str]:
        return {"renderer": "painter-sprite", "version": "1"}

    def close(self) -> None:
        return None

    # -- Painting -------------------------------------------------------------

    def paint(self, painter: QPainter, rect: QRectF, snapshot: CompanionSnapshot) -> None:
        """Paint the character into rect for the given snapshot."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        now = time.monotonic()
        if self._last_paint is None:
            self._last_paint = now
        delta = min(0.25, now - self._last_paint)
        self._last_paint = now
        self._eye_phase = (self._eye_phase + delta) % 4.0

        body_rect = self._body_rect(rect, snapshot)
        self._draw_body(painter, body_rect, snapshot)
        self._draw_face(painter, body_rect, snapshot, now)
        if snapshot.status_text:
            self._draw_status_bubble(painter, rect, snapshot.status_text)
        painter.restore()

    # -- Geometry -------------------------------------------------------------

    def _body_rect(self, rect: QRectF, snapshot: CompanionSnapshot) -> QRectF:
        """Centered body with a breathing scale and a broken-down error look."""
        scale = 1.0
        if snapshot.mode == CompanionMode.IDLE:
            scale = 1.0 + 0.02 * math.sin(time.monotonic() * 2.0)
        elif snapshot.mode == CompanionMode.SPEAKING:
            scale = 1.0 + 0.04 * abs(math.sin(time.monotonic() * 6.0))
        elif snapshot.mode == CompanionMode.ERROR:
            scale = 0.94
        center = rect.center()
        side = min(rect.width(), rect.height()) * 0.72 * scale
        return QRectF(
            center.x() - side / 2,
            center.y() - side / 2,
            side,
            side * 0.86,
        )

    # -- Parts ----------------------------------------------------------------

    def _draw_body(self, painter: QPainter, body: QRectF, snapshot: CompanionSnapshot) -> None:
        glow = ERROR_COLOR if snapshot.mode == CompanionMode.ERROR else GLOW_COLOR
        path = self._body_path(body)
        halo = QRadialGradient(body.center(), body.width() * 0.75)
        halo_color = QColor(glow)
        halo_color.setAlpha(70 if snapshot.mode == CompanionMode.ERROR else 46)
        halo.setColorAt(0.55, QColor(0, 0, 0, 0))
        halo.setColorAt(1.0, halo_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(body.adjusted(-body.width() * 0.3, -body.height() * 0.3, body.width() * 0.3, body.height() * 0.3))

        gradient = QRadialGradient(body.center().x(), body.top(), body.height())
        gradient.setColorAt(0.0, BODY_COLOR.lighter(130))
        gradient.setColorAt(1.0, QColor("#17181B"))
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(BODY_EDGE, 2))
        painter.drawPath(path)

        if snapshot.mode == CompanionMode.LISTENING:
            painter.setBrush(QBrush(BODY_EDGE))
            painter.setPen(Qt.PenStyle.NoPen)
            for sign in (-1.0, 1.0):
                tip = QPointF(
                    body.center().x() + sign * body.width() * 0.34,
                    body.top() - body.height() * 0.28,
                )
                painter.drawPolygon(
                    [QPointF(tip.x() - 5, body.top() + 2), QPointF(tip.x() + 5, body.top() + 2), tip]
                )

    def _body_path(self, body: QRectF) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(body)
        return path

    def _draw_face(
        self, painter: QPainter, body: QRectF, snapshot: CompanionSnapshot, now: float
    ) -> None:
        if snapshot.mode == CompanionMode.ERROR:
            eye_color = ERROR_COLOR
        elif snapshot.mode == CompanionMode.LISTENING:
            eye_color = QColor("#F2D2B0")
        else:
            eye_color = GLOW_COLOR

        gaze = self._gaze_offset(snapshot)
        blink = self._blink_progress(now)
        if snapshot.status_text and snapshot.status_text.startswith("Zzz"):
            # Dozing: heavy lids, dim eyes.
            blink = 0.75
            eye_color = SLEEP_COLOR

        eye_y = body.top() + body.height() * 0.36
        eye_dx = body.width() * 0.2
        eye_r = body.width() * 0.09
        for sign in (-1.0, 1.0):
            cx = body.center().x() + sign * eye_dx + gaze.x() * body.width() * 0.04
            cy = eye_y + gaze.y() * body.height() * 0.03
            painter.setBrush(QBrush(eye_color))
            painter.setPen(Qt.PenStyle.NoPen)
            height = max(1.0, eye_r * 2.0 * (1.0 - blink))
            painter.drawEllipse(QPointF(cx, cy), eye_r, height / 2)

        if snapshot.emotion == "sad":
            self._draw_mouth(painter, body, curve=-1.0, weight=0.6)
        elif snapshot.emotion == "happy":
            self._draw_mouth(painter, body, curve=1.0, weight=0.6)
        else:
            self._draw_mouth(painter, body, curve=0.0, weight=snapshot.mouth_weight)

    def _draw_mouth(self, painter: QPainter, body: QRectF, curve: float, weight: float) -> None:
        cx, cy = body.center().x(), body.top() + body.height() * 0.62
        width = body.width() * 0.22
        if weight <= 0.01 and curve == 0.0:
            painter.setPen(QPen(BODY_EDGE, 2))
            painter.drawLine(QPointF(cx - width / 2, cy), QPointF(cx + width / 2, cy))
            return
        path = QPainterPath()
        path.moveTo(cx - width / 2, cy)
        path.quadTo(
            QPointF(cx, cy + curve * weight * body.height() * 0.16 + weight * body.height() * 0.05),
            QPointF(cx + width / 2, cy),
        )
        painter.setPen(QPen(QColor("#1A140F"), 2))
        painter.setBrush(QBrush(QColor("#1A140F")))
        painter.drawPath(path)

    def _gaze_offset(self, snapshot: CompanionSnapshot) -> QPointF:
        return QPointF(snapshot.gaze_x, snapshot.gaze_y)

    def _blink_progress(self, now: float) -> float:
        """0 = open eyes, 1 = fully closed; a quick blink every ~4 seconds."""
        cycle = now % 4.0
        if cycle < 0.12:
            return math.sin(cycle / 0.12 * math.pi)
        return 0.0

    def _draw_status_bubble(self, painter: QPainter, rect: QRectF, text: str) -> None:
        text = text if len(text) <= 60 else text[:57].rstrip() + "…"
        font = QFont()
        font.setPixelSize(14)
        font.setWeight(QFont.Weight.Medium)
        metrics = QFontMetrics(font)
        width = max(72, min(rect.width() * 1.6, metrics.horizontalAdvance(text) + 24))
        height = 30
        bubble = QRectF(
            rect.center().x() - width / 2,
            rect.top() + 2,
            width,
            height,
        )
        path = QPainterPath()
        path.addRoundedRect(bubble, 12, 12)
        painter.setBrush(QBrush(BUBBLE_BG))
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.drawPath(path)
        painter.setFont(font)
        painter.setPen(QPen(BUBBLE_TEXT))
        painter.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)
