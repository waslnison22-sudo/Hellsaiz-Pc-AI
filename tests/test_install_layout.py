from __future__ import annotations

import json
from pathlib import Path

from hellsaiz_pc_ai import launcher
from hellsaiz_pc_ai.install_layout import installed_version


def test_installed_version_falls_back_when_active_json_is_not_an_object(tmp_path: Path):
    (tmp_path / "active.json").write_text("[]", encoding="utf-8")

    assert installed_version(tmp_path, fallback="0.0.0") == "0.0.0"


def test_installed_version_falls_back_when_active_version_has_wrong_type(tmp_path: Path):
    (tmp_path / "active.json").write_text(
        json.dumps({"active_version": 123}), encoding="utf-8"
    )

    assert installed_version(tmp_path, fallback="0.0.0") == "0.0.0"


def test_launcher_shows_recovery_error_for_non_object_active_json(tmp_path: Path, monkeypatch):
    (tmp_path / "active.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "HellsaizLauncher.exe"))
    errors: list[str] = []
    monkeypatch.setattr(launcher, "_show_error", errors.append)

    assert launcher.main() == 2
    assert errors and "active.json" in errors[0]


def test_launcher_starts_the_active_version(tmp_path: Path, monkeypatch):
    version_dir = tmp_path / "versions" / "0.1.2"
    version_dir.mkdir(parents=True)
    app_executable = version_dir / "HellsaizPC_AI.exe"
    app_executable.write_bytes(b"test")
    (tmp_path / "active.json").write_text(
        json.dumps({"schema_version": 1, "active_version": "0.1.2"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(launcher.sys, "executable", str(tmp_path / "HellsaizLauncher.exe"))
    launches: list[tuple[list[str], dict[str, object]]] = []

    def fake_popen(command, **kwargs):
        launches.append((command, kwargs))
        return None

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    assert launcher.main() == 0
    assert launches[0][0][0] == str(app_executable.resolve())
    assert launches[0][1]["cwd"] == str(version_dir.resolve())
