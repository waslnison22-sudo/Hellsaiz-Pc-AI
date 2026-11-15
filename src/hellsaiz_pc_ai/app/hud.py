from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget


class AnimatedPageStack(QStackedWidget):
    """A QStackedWidget with short, interruptible cross-fade page transitions."""

    def __init__(self, parent=None, duration_ms: int = 160) -> None:
        super().__init__(parent)
        self.duration_ms = max(0, min(int(duration_ms), 400))
        self.animations_enabled = True
        self._animation: QPropertyAnimation | None = None
        self._active_effect: QGraphicsOpacityEffect | None = None

    def set_animations_enabled(self, enabled: bool) -> None:
        self.animations_enabled = bool(enabled)
        if not self.animations_enabled:
            self._finish_transition()

    def _finish_transition(self) -> None:
        animation = self._animation
        self._animation = None
        if animation is not None:
            animation.stop()
            animation.deleteLater()
        if self._active_effect is not None:
            self._active_effect.setOpacity(1.0)
            self._active_effect = None

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802 - Qt API name
        if index < 0 or index >= self.count() or index == self.currentIndex():
            super().setCurrentIndex(index)
            return

        self._finish_transition()
        next_page = self.widget(index)
        if (
            not self.animations_enabled
            or self.duration_ms == 0
            or not self.isVisible()
            or next_page is None
        ):
            super().setCurrentIndex(index)
            return

        effect = next_page.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(next_page)
            next_page.setGraphicsEffect(effect)

        effect.setOpacity(0.0)
        super().setCurrentIndex(index)

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(self.duration_ms)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(self._finish_transition)
        self._active_effect = effect
        self._animation = animation
        animation.start()
