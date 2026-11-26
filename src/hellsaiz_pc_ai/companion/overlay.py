"""Transparent always-on-top overlay window hosting the companion.

Phase 1 of the companion plan: the overlay lives in the existing assistant
process, shows only the character (no chrome), remembers its position and
size, drifts into a doze when nothing happens and snaps to screen edges.
Renderer failure must never take the assistant down — every paint is guarded.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QMenu, QWidget

from hellsaiz_pc_ai.companion.contracts import CompanionMode, CompanionSnapshot
from hellsaiz_pc_ai.companion.sprite_renderer import BASE_SIZE, PainterSpriteRenderer


class CompanionOverlay(QWidget):
    """Frameless translucent window that paints the companion character."""

    ANIMATION_INTERVAL_MS = 40
    DOZE_TIMEOUT_S = 180.0
    EDGE_SNAP_MARGIN = 24.0
    MIN_SCALE = 0.5
    MAX_SCALE = 2.5

    def __init__(
        self,
        snapshot_provider: Any,
        *,
        state_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._snapshot_provider = snapshot_provider
        self._renderer = PainterSpriteRenderer()
        self._state_path = state_path
        self._scale = 1.0
        self._drag_offset: QPoint | None = None
        self._last_activity = time.monotonic()
        self._dozing = False
        self._visible_by_user = True
        self._privacy_mode = False
        self._obs_mode = False
        self._gaze = (0.0, 0.0)

        self.setObjectName("companionOverlay")
        # Order matters on Windows: attributes before window flags/show.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedSize(int(BASE_SIZE * self._scale), int(BASE_SIZE * self._scale))
        self._restore_state()

        self._timer = QTimer(self)
        self._timer.setInterval(self.ANIMATION_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # -- State persistence -----------------------------------------------------

    def _restore_state(self) -> None:
        if self._state_path is None:
            return
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            logging.debug("Companion state is unreadable; using defaults.")
            return
        if not isinstance(raw, dict):
            return
        position = raw.get("position")
        if isinstance(position, dict):
            x, y = position.get("x"), position.get("y")
            if isinstance(x, int) and isinstance(y, int):
                self.move(QPoint(x, y))
        scale = raw.get("scale")
        if isinstance(scale, (int, float)) and self.MIN_SCALE <= scale <= self.MAX_SCALE:
            # Resize without moving: position is restored afterwards, verbatim.
            self._scale = float(scale)
            self.setFixedSize(int(BASE_SIZE * scale), int(BASE_SIZE * scale))
        if raw.get("hidden") is True:
            self._visible_by_user = False

    def save_state(self) -> None:
        if self._state_path is None:
            return
        payload: dict = {}
        if self._state_path is not None and self._state_path.is_file():
            try:
                existing = json.loads(self._state_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    payload = existing
            except (OSError, ValueError, json.JSONDecodeError):
                payload = {}
        payload["position"] = {"x": self.x(), "y": self.y()}
        payload["scale"] = self._scale
        payload["hidden"] = not self._visible_by_user
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            logging.exception("Could not persist companion state.")

    # -- Lifecycle --------------------------------------------------------------

    def showEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self.setVisible(self._visible_by_user)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        self.save_state()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._timer.stop()
        self.save_state()

    def set_visible(self, visible: bool) -> None:
        """Show or hide the companion explicitly (persisted in companion.json)."""
        self._visible_by_user = bool(visible)
        self.setVisible(self._visible_by_user)
        self.save_state()

    def toggle_visibility(self) -> None:
        self.set_visible(not self._visible_by_user)

    def set_privacy_mode(self, enabled: bool) -> None:
        """Privacy mode: the gaze freezes and the face stays neutral."""
        self._privacy_mode = bool(enabled)
        if self._privacy_mode:
            self._gaze = (0.0, 0.0)
            try:
                self._controller_set_gaze = getattr(self, "_controller_set_gaze", None)
            except AttributeError:
                pass
        self.update()

    def set_obs_mode(self, enabled: bool) -> None:
        """Stream mode: clicks pass through so OBS captures the sprite cleanly."""
        self._obs_mode = bool(enabled)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, self._obs_mode)
        self.update()

    @property
    def privacy_mode(self) -> bool:
        return self._privacy_mode

    @property
    def obs_mode(self) -> bool:
        return self._obs_mode

    def snapshot(self) -> CompanionSnapshot:
        return self._snapshot_provider() if self._snapshot_provider else CompanionSnapshot()

    # -- Animation loop -----------------------------------------------------------

    def _tick(self) -> None:
        if not self.isVisible():
            return
        snap = self.snapshot()
        if snap.mode != CompanionMode.IDLE or self._cursor_nearby():
            self._last_activity = time.monotonic()
        self._dozing = (
            snap.mode == CompanionMode.IDLE
            and not self._cursor_nearby()
            and (time.monotonic() - self._last_activity) > self.DOZE_TIMEOUT_S
        )
        self.update()

    def _cursor_nearby(self) -> bool:
        from PySide6.QtGui import QCursor

        cursor = QCursor.pos()
        center = self.mapToGlobal(self.rect().center())
        dx, dy = cursor.x() - center.x(), cursor.y() - center.y()
        return math.hypot(dx, dy) < self.width()

    # -- Painting ------------------------------------------------------------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        snapshot = self.snapshot()
        if self._dozing:
            snapshot = CompanionSnapshot(
                mode=snapshot.mode,
                emotion=snapshot.emotion,
                viseme=snapshot.viseme,
                emotion_weight=snapshot.emotion_weight,
                mouth_weight=snapshot.mouth_weight,
                gaze_x=snapshot.gaze_x,
                gaze_y=snapshot.gaze_y,
                status_text="Zzz…",
            )
        try:
            self._renderer.paint(painter, QRectF(self.rect()), snapshot)
        except Exception:  # noqa: BLE001 - a broken frame must not kill the app
            logging.exception("Companion paint failed; skipping the frame.")

    # -- Interaction ---------------------------------------------------------------

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._last_activity = time.monotonic()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        if self._drag_offset is not None:
            self._drag_offset = None
            self._snap_to_edge()
            self.save_state()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.MouseButton.LeftButton and not self._obs_mode:
            self._last_activity = time.monotonic()
            pet = getattr(self, "on_pet", None)
            if callable(pet):
                try:
                    pet()
                except Exception:  # noqa: BLE001 - interaction must not crash the overlay
                    logging.exception("Companion pet handler failed.")
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        delta = 0.1 if event.angleDelta().y() > 0 else -0.1
        self._apply_scale(min(self.MAX_SCALE, max(self.MIN_SCALE, self._scale + delta)))
        self._last_activity = time.monotonic()
        self.save_state()
        event.accept()

    def contextMenuEvent(self, event: Any) -> None:  # noqa: N802 (Qt naming)
        menu = QMenu(self)
        menu.addAction("Скрыть", self.toggle_visibility)
        menu.addAction("Сбросить размер", lambda: self._apply_scale(1.0))
        menu.exec(event.globalPos())
        event.accept()

    def _apply_scale(self, scale: float) -> None:
        clamped = min(self.MAX_SCALE, max(self.MIN_SCALE, scale))
        if clamped == self._scale:
            return
        center = self.geometry().center()
        self._scale = clamped
        self.setFixedSize(int(BASE_SIZE * clamped), int(BASE_SIZE * clamped))
        target = self.geometry()
        target.moveCenter(center)
        self.setGeometry(target)

    def _snap_to_edge(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x, y = self.x(), self.y()
        if self.x() - geometry.left() <= self.EDGE_SNAP_MARGIN:
            x = geometry.left() + 8
        elif geometry.right() - (self.x() + self.width()) <= self.EDGE_SNAP_MARGIN:
            x = geometry.right() - self.width() - 8
        if self.y() - geometry.top() <= self.EDGE_SNAP_MARGIN:
            y = geometry.top() + 8
        elif geometry.bottom() - (self.y() + self.height()) <= self.EDGE_SNAP_MARGIN:
            y = geometry.bottom() - self.height() - 8
        self.move(x, y)

    def gaze_toward(self, global_point: QPointF) -> None:
        """Utility for tests and future drivers: aim the character's gaze."""
        self._last_activity = time.monotonic()
