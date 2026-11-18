from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apply_pending_patches.py"
_SPEC = importlib.util.spec_from_file_location("apply_pending_patches", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

_load_workflow_state = _MODULE._load_workflow_state
_save_workflow_state = _MODULE._save_workflow_state
_workflow_state_path = _MODULE._workflow_state_path
_patch_sort_key = _MODULE._patch_sort_key


def test_stage_patches_sort_by_numeric_stage(tmp_path):
    names = (
        "stage10_startup_telemetry.patch",
        "stage1_desktop_ui_workers.patch",
        "stage1b_dead_imports.patch",
        "stage2_vpn_tools.patch",
        "stage9_sapi5_delayed_start.patch",
    )
    for name in names:
        (tmp_path / name).write_text("", encoding="utf-8")

    ordered = [patch.name for patch in sorted(tmp_path.glob("*.patch"), key=_patch_sort_key)]

    assert ordered == [
        "stage1_desktop_ui_workers.patch",
        "stage1b_dead_imports.patch",
        "stage2_vpn_tools.patch",
        "stage9_sapi5_delayed_start.patch",
        "stage10_startup_telemetry.patch",
    ]


def test_patch_state_is_scoped_to_github_run(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.chdir(tmp_path)

    path = _workflow_state_path()

    assert path is not None
    assert path.name.startswith("hellsaiz-patches-12345-2-")


def test_patch_state_round_trips(tmp_path):
    path = tmp_path / "patch-state.json"
    state = {"stage1.patch": "abc123", "stage2.patch": "def456"}

    _save_workflow_state(path, state)

    assert _load_workflow_state(path) == state


def test_patch_state_ignores_corrupt_json(tmp_path):
    path = tmp_path / "patch-state.json"
    path.write_text("{broken", encoding="utf-8")

    assert _load_workflow_state(path) == {}
