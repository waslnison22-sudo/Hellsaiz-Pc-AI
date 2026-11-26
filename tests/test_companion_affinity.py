"""Companion affinity, phrases and phase-2 overlay contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from hellsaiz_pc_ai.companion.affinity import (
    LEVELS,
    POINTS_PER_LEVEL,
    AffinityTracker,
)
from hellsaiz_pc_ai.companion.phrases import MAX_PHRASE_LEN, PHRASES, phrase_for

try:  # PySide6 widgets are unavailable on headless Linux runners.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from hellsaiz_pc_ai.companion.controller import CompanionController
    from hellsaiz_pc_ai.companion.overlay import CompanionOverlay

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


def test_levels_grow_with_points(tmp_path: Path):
    tracker = AffinityTracker(tmp_path / "companion.json")

    assert tracker.level() == LEVELS[0]
    tracker.add_points(POINTS_PER_LEVEL)
    assert tracker.level() == LEVELS[1]
    tracker.add_points(POINTS_PER_LEVEL * 10)
    assert tracker.level() == LEVELS[-1]


def test_points_persist_and_merge_with_overlay_payload(tmp_path: Path):
    state = tmp_path / "companion.json"
    state.write_text('{"position": {"x": 10, "y": 20}, "scale": 1.0, "hidden": false}')
    tracker = AffinityTracker(state)

    tracker.add_points(7)

    import json

    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["affinity_points"] == 7
    assert payload["position"] == {"x": 10, "y": 20}
    assert AffinityTracker(state).points == 7


def test_daily_activity_counts_once_per_date(tmp_path: Path):
    today = {"value": "2026-11-26"}
    tracker = AffinityTracker(tmp_path / "companion.json", today=lambda: today["value"])

    assert tracker.register_daily_activity() is True
    start = tracker.points
    assert tracker.register_daily_activity() is False
    assert tracker.points == start
    today["value"] = "2026-11-27"
    assert tracker.register_daily_activity() is True


def test_corrupt_state_falls_back_to_zero(tmp_path: Path):
    state = tmp_path / "companion.json"
    state.write_text("{not json")
    tracker = AffinityTracker(state)

    assert tracker.points == 0
    assert tracker.level() == LEVELS[0]


def test_subscribe_notifies_and_can_unsubscribe(tmp_path: Path):
    tracker = AffinityTracker(tmp_path / "companion.json")
    seen: list[tuple[int, str]] = []
    unsubscribe = tracker.subscribe(lambda points, level: seen.append((points, level)))

    tracker.add_points(3)
    unsubscribe()
    tracker.add_points(3)

    assert len(seen) == 1
    assert seen[0] == (3, LEVELS[0])


def test_phrases_are_short_and_cover_events():
    for event, variants in PHRASES.items():
        assert variants, event
        for line in variants:
            assert len(line) <= MAX_PHRASE_LEN, line
    assert phrase_for("unknown-event") == ""
    assert phrase_for("pet", seed=1) in PHRASES["pet"]


@requires_qt
def test_obs_mode_sets_the_transparent_attribute(tmp_path: Path):
    QApplication.instance() or QApplication([])
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=tmp_path / "c.json")

    overlay.set_obs_mode(True)

    assert overlay.obs_mode is True
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is True
    overlay.set_obs_mode(False)
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents) is False
    overlay.shutdown()


@requires_qt
def test_privacy_mode_freezes_the_gaze(tmp_path: Path):
    QApplication.instance() or QApplication([])
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=tmp_path / "c.json")

    overlay.set_privacy_mode(True)

    assert overlay.privacy_mode is True
    overlay.shutdown()


@requires_qt
def test_double_click_triggers_petting(tmp_path: Path):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    QApplication.instance() or QApplication([])
    overlay = CompanionOverlay(CompanionController().snapshot, state_path=tmp_path / "c.json")
    calls: list[int] = []
    overlay.on_pet = lambda: calls.append(1)
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonDblClick,
        QPointF(10, 10),
        QPointF(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )

    overlay.mouseDoubleClickEvent(event)

    assert calls == [1]
    overlay.shutdown()
