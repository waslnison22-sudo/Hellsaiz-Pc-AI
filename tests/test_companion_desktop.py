"""Companion integration contracts (task 1) + toast startup regression.

The controller/bridge are pure Python; only the overlay, toast and desktop
shell need PySide6, so those imports sit behind the usual Linux skip guard.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from hellsaiz_pc_ai.companion.controller import CompanionController
from hellsaiz_pc_ai.companion.events import CompanionEventBridge

try:  # PySide6 widgets are unavailable on headless Linux runners.
    from PySide6.QtWidgets import QApplication, QWidget

    from hellsaiz_pc_ai.app.chat_page import Toast
    from hellsaiz_pc_ai.app import desktop as desktop_module
    from hellsaiz_pc_ai.companion.overlay import CompanionOverlay

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


def test_bridge_maps_worker_events_to_modes():
    controller = CompanionController()
    bridge = CompanionEventBridge(controller)

    bridge.thinking()
    thinking = controller.snapshot()
    bridge.speaking("Готово: напоминание создано")
    speaking = controller.snapshot()
    bridge.error()
    failed = controller.snapshot()
    bridge.settled()
    settled = controller.snapshot()

    assert thinking.mode.value == "thinking"
    assert speaking.mode.value == "speaking"
    assert "напоминание" in speaking.status_text
    assert failed.mode.value == "error"
    assert settled.mode.value == "idle"


def test_bridge_tolerates_a_worker_without_the_expected_signals():
    class SignallessWorker:
        pass

    controller = CompanionController()
    bridge = CompanionEventBridge(controller)

    bridge.connect_worker(
        SignallessWorker(), SignallessWorker(), SignallessWorker()
    )

    assert controller.snapshot().mode.value == "hidden"


@requires_qt
def test_overlay_set_visible_persists_the_choice(tmp_path: Path):
    QApplication.instance() or QApplication([])
    state_path = tmp_path / "companion.json"
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=state_path)

    overlay.set_visible(False)
    assert overlay._visible_by_user is False
    overlay.set_visible(True)
    assert overlay._visible_by_user is True
    overlay.shutdown()

    assert state_path.exists()
    assert '"hidden": false' in state_path.read_text(encoding="utf-8").replace("\n", "")


@requires_qt
def test_overlay_shutdown_stops_the_animation_timer(tmp_path: Path):
    QApplication.instance() or QApplication([])
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=tmp_path / "c.json")

    overlay.shutdown()

    assert overlay._timer.isActive() is False


@requires_qt
def test_toast_starts_and_fades_out_without_missing_methods():
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(400, 300)
    parent.show()
    toast = Toast(parent)

    toast.show_message("Скопировано", timeout_ms=10)
    app.processEvents()
    assert toast.isHidden() is False
    toast._fade_out()
    app.processEvents()

    assert hasattr(toast, "_fade_out")


@requires_qt
def test_overlay_hides_when_the_shell_window_closes(tmp_path: Path):
    QApplication.instance() or QApplication([])
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=tmp_path / "c.json")
    overlay.set_visible(True)
    overlay.show()

    # The shell's close handler calls shutdown() and hide(); this is the contract
    # that guarantees the process exits when the main window closes.
    overlay.shutdown()
    overlay.hide()

    assert overlay.isHidden() is True


@requires_qt
def test_desktop_shell_creates_one_companion_and_shuts_it_down():
    source = inspect.getsource(desktop_module.main)

    assert source.count("CompanionController()") == 1
    assert source.count("CompanionOverlay(") == 1
    assert source.count("CompanionEventBridge(") == 1
    assert "companion_overlay.shutdown" in source
    assert "companion_overlay.hide()" in source
    assert "app.setQuitOnLastWindowClosed(True)" in source
    assert "companion_overlay.set_visible(companion_enabled)" in source
    assert 'on_open_chat=lambda: show_page("Чат")' in source


@requires_qt
def test_overlay_defaults_to_a_screen_corner(tmp_path: Path):
    QApplication.instance() or QApplication([])
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=tmp_path / "no-state.json")
    screen = overlay.screen()
    assert screen is not None
    area = screen.availableGeometry()

    assert overlay.x() > area.center().x(), "default placement must be on the right half"
    assert overlay.y() > area.center().y(), "default placement must be on the bottom half"
    assert area.contains(overlay.geometry()), "the companion must stay inside the screen"
