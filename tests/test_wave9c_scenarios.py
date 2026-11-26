"""Wave-9C contracts: scenario CTA, launch gating and delete gating."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STUDIO_SOURCE = REPO / "src" / "hellsaiz_pc_ai" / "app" / "workflow_studio.py"

try:  # PySide6 widgets are unavailable on headless Linux runners.
    from hellsaiz_pc_ai.app.workflow_studio import WorkflowStudioPage, launch_state

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover - runner-specific
    _QT_AVAILABLE = False

requires_qt = pytest.mark.skipif(
    not _QT_AVAILABLE, reason="PySide6 GUI libraries are not available on this runner"
)


class _FakeButton:
    def __init__(self) -> None:
        self.enabled = None

    def setEnabled(self, value: bool) -> None:  # noqa: N802 (Qt naming)
        self.enabled = value


# ------------------------------------------------------------------ scenario gating


def test_studio_has_cta_gating_helpers():
    source = STUDIO_SOURCE.read_text(encoding="utf-8")

    assert "def _empty_actions_placeholder" in source
    assert 'add_button = QPushButton("Добавить действие")' in source
    assert "Приложения, Система, Звук, " in source
    assert "def _actions_total" in source
    assert "def _update_launch_state" in source
    assert "def _update_library_actions" in source
    assert 'launch_state(' in source
    assert '"Добавь хотя бы одно действие"' in source
    assert '"Сценарий готов к запуску"' in source


@requires_qt
def test_launch_gate_follows_actions_not_widget_state():
    assert launch_state(0, has_workflow=True, editable=True) == (
        False,
        "Добавь хотя бы одно действие",
    )
    assert launch_state(1, has_workflow=True, editable=True) == (
        True,
        "Сценарий готов к запуску",
    )
    assert launch_state(2, has_workflow=False, editable=True) == (
        False,
        "Сначала сохрани сценарий",
    )
    assert launch_state(0, has_workflow=True, editable=False) == (
        True,
        "Сложный сценарий: запуск доступен.",
    )


@requires_qt
def test_delete_button_needs_a_library_selection():
    from types import SimpleNamespace

    page = SimpleNamespace(
        delete_button=_FakeButton(),
        scenario_list=SimpleNamespace(selectedItems=lambda: []),
    )
    WorkflowStudioPage._update_library_actions(page)
    assert page.delete_button.enabled is False

    page.scenario_list = SimpleNamespace(selectedItems=lambda: ["item"])
    WorkflowStudioPage._update_library_actions(page)
    assert page.delete_button.enabled is True
