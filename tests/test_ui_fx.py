"""Tests for the micro-animation helpers."""

from __future__ import annotations

import pytest

try:  # PySide6 GUI libraries are absent on headless Linux runners.
    from hellsaiz_pc_ai.app import ui_fx
except ImportError as exc:  # pragma: no cover - runner-specific
    pytest.skip(f"Qt native libraries unavailable: {exc}", allow_module_level=True)

try:  # PySide6 GUI libraries are absent on headless Linux runners.
    from PySide6.QtCore import QVariantAnimation
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

_requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


def test_reduce_motion_is_off_without_an_application():
    assert ui_fx.reduce_motion() is False


@_requires_qt
def test_install_button_fx_is_skipped_when_motion_is_reduced(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui_fx, "reduce_motion", lambda: True)
    button = QPushButton("test")

    assert ui_fx.install_button_fx(button) is None


@_requires_qt
def test_button_fx_stops_the_animation_when_hidden(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui_fx, "reduce_motion", lambda: False)
    button = QPushButton("test")
    button.show()
    app.processEvents()
    fx = ui_fx.install_button_fx(button)

    assert fx is not None
    fx._animate_to(fx.hover_color)
    assert fx._animation.state() == QVariantAnimation.State.Running
    button.hide()
    app.processEvents()

    assert fx._animation.state() != QVariantAnimation.State.Running


@_requires_qt
def test_animate_height_is_instant_when_motion_is_reduced(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui_fx, "reduce_motion", lambda: True)
    from PySide6.QtWidgets import QLabel, QVBoxLayout

    container = QWidget()
    layout = QVBoxLayout(container)
    layout.addWidget(QLabel("collapsible content"))

    ui_fx.animate_height(container, True)

    assert container.isVisible() is True
    assert container.maximumHeight() > 0
    ui_fx.animate_height(container, False)
    assert container.isVisible() is False


@_requires_qt
def test_pulse_dot_does_not_start_with_reduced_motion(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui_fx, "reduce_motion", lambda: True)
    from PySide6.QtWidgets import QLabel

    dot = QLabel("●")
    pulse = ui_fx.PulseDot(dot)

    pulse.start()

    assert pulse._animation.state() != QVariantAnimation.State.Running


@_requires_qt
def test_chevron_pixmap_renders():
    QApplication.instance() or QApplication([])

    pixmap = ui_fx.chevron_pixmap(90.0)

    assert pixmap.isNull() is False
    assert pixmap.size().width() == 16
