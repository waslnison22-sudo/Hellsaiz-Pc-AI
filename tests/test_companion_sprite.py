"""Companion phase-1 contracts: painter renderer, overlay behaviour, persistence."""

from __future__ import annotations

import json

import pytest

from hellsaiz_pc_ai.companion.contracts import CompanionMode, CompanionSnapshot
from hellsaiz_pc_ai.companion.controller import CompanionController

try:  # Qt widgets need libEGL on Linux; skip there, full run on Windows.
    from PySide6.QtCore import QPoint, QRectF, Qt
    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.companion.overlay import CompanionOverlay
    from hellsaiz_pc_ai.companion.sprite_renderer import BASE_SIZE, PainterSpriteRenderer

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_renderer_paints_every_mode_and_emotion(qapp):
    assert qapp is not None
    from PySide6.QtGui import QPixmap

    renderer = PainterSpriteRenderer()
    for mode in CompanionMode:
        for emotion in (
            "neutral", "happy", "sad", "surprised", "angry", "confused", "curious",
        ):
            snapshot = CompanionSnapshot(mode=mode, emotion=emotion)
            pixmap = QPixmap(160, 160)
            pixmap.fill(Qt.GlobalColor.transparent)
            from PySide6.QtGui import QPainter

            painter = QPainter(pixmap)
            renderer.paint(painter, QRectF(0, 0, 160, 160), snapshot)
            painter.end()
            assert not pixmap.isNull(), (mode, emotion)


def test_renderer_paints_a_status_bubble(qapp):
    from PySide6.QtGui import QPainter, QPixmap

    renderer = PainterSpriteRenderer()
    snapshot = CompanionSnapshot(mode=CompanionMode.THINKING, status_text="Думаю")
    pixmap = QPixmap(240, 160)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.paint(painter, QRectF(0, 0, 240, 160), snapshot)
    painter.end()
    assert not pixmap.isNull()
    assert renderer.render_status()["renderer"] == "painter-sprite"


def test_overlay_window_flags_and_translucency(qapp):
    assert qapp is not None
    overlay = CompanionOverlay(CompanionController().snapshot)
    assert bool(overlay.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert bool(overlay.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_overlay_persists_position_scale_and_visibility(tmp_path, qapp):
    assert qapp is not None
    state_path = tmp_path / "companion.json"
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=state_path)
    overlay._apply_scale(1.5)
    overlay.move(QPoint(40, 60))
    overlay.save_state()
    assert state_path.exists()

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["position"] == {"x": 40, "y": 60}
    assert payload["scale"] == 1.5

    restored = CompanionOverlay(CompanionController().snapshot, state_path=state_path)
    assert restored.pos() == QPoint(40, 60)
    assert restored._scale == 1.5


def test_overlay_corrupt_state_falls_back_to_defaults(tmp_path, qapp):
    assert qapp is not None
    state_path = tmp_path / "companion.json"
    state_path.write_text("{ not json", encoding="utf-8")
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=state_path)
    assert overlay._scale == 1.0


def test_overlay_snaps_to_screen_edge(tmp_path, qapp):
    assert qapp is not None
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=tmp_path / "s.json")
    overlay._apply_scale(1.0)
    screen = overlay.screen()
    assert screen is not None
    geo = screen.availableGeometry()
    # Drag near the right edge and release: it must clamp inside the screen.
    overlay.move(geo.right() - 4, geo.top() + 40)
    overlay._drag_offset = QPoint(0, 0)
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(10, 10),
        QPointF(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release)
    assert overlay.x() + overlay.width() <= geo.right() + 1
    assert overlay.x() >= geo.right() - overlay.width() - 20


def test_overlay_follows_controller_snapshots(qapp):
    assert qapp is not None
    controller = CompanionController()
    overlay = CompanionOverlay(controller.snapshot, state_path=None)
    controller.set_mode(CompanionMode.LISTENING, "Слушаю")
    assert overlay.snapshot().mode == CompanionMode.LISTENING
    controller.reset()
    assert overlay.snapshot().mode == CompanionMode.IDLE


def test_doze_only_after_long_idle(qapp, monkeypatch):
    assert qapp is not None
    controller = CompanionController()
    controller.set_mode(CompanionMode.IDLE)
    overlay = CompanionOverlay(controller.snapshot, state_path=None)
    overlay.show()
    clock = {"now": 100.0}

    def fake_monotonic():
        return clock["now"]

    monkeypatch.setattr("hellsaiz_pc_ai.companion.overlay.time.monotonic", fake_monotonic)
    monkeypatch.setattr(overlay, "_cursor_nearby", lambda: False)
    overlay._last_activity = clock["now"]
    clock["now"] += overlay.DOZE_TIMEOUT_S + 1.0
    overlay._tick()
    assert overlay._dozing is True


def test_default_painter_character_needs_no_files():
    renderer = PainterSpriteRenderer()
    renderer.load_model("", "")
    assert renderer.render_status() == {"renderer": "painter-sprite", "version": "1"}
    assert BASE_SIZE == 128


def test_painter_sprite_never_touches_the_window_edges(qapp):
    """Regression: the halo and the status bubble must stay inside 128x128."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QImage, QPainter

    renderer = PainterSpriteRenderer()
    edge_hits: list[str] = []
    for mode in CompanionMode:
        snapshot = CompanionSnapshot(mode=mode, status_text="Проверка" if mode == CompanionMode.SPEAKING else "")
        image = QImage(BASE_SIZE, BASE_SIZE, QImage.Format.Format_ARGB32)
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        try:
            renderer.paint(painter, QRectF(0, 0, BASE_SIZE, BASE_SIZE), snapshot)
        finally:
            painter.end()
        last = BASE_SIZE - 1
        border_hits = 0
        for x in range(BASE_SIZE):
            for y in (0, last):
                if image.pixelColor(x, y).alpha() > 0:
                    border_hits += 1
        for y in range(BASE_SIZE):
            for x in (0, last):
                if image.pixelColor(x, y).alpha() > 0:
                    border_hits += 1
        if border_hits:
            edge_hits.append(f"{mode.value}: {border_hits} edge pixels")

    assert edge_hits == [], edge_hits
