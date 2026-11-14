from pathlib import Path
import subprocess

from hellsaiz_pc_ai.app import shortcuts


def test_shortcut_is_skipped_outside_windows(tmp_path: Path):
    launcher = tmp_path / "HellsaizLauncher.exe"
    launcher.write_bytes(b"launcher")

    assert shortcuts.ensure_desktop_shortcut(launcher, is_windows=False) is False


def test_shortcut_targets_the_stable_launcher_and_uses_safe_environment(tmp_path: Path, monkeypatch):
    launcher = tmp_path / "HellsaizLauncher.exe"
    launcher.write_bytes(b"launcher")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(shortcuts.subprocess, "run", fake_run)

    assert shortcuts.ensure_desktop_shortcut(launcher, is_windows=True) is True
    assert captured["command"][0] == "powershell.exe"
    assert captured["check"] is True
    assert captured["timeout"] == 15
    assert captured["env"]["HELLSAIZ_LAUNCHER_PATH"] == str(launcher.resolve())
    assert "CreateShortcut" in captured["command"][-1]
    assert "$env:HELLSAIZ_LAUNCHER_PATH" in captured["command"][-1]


def test_shortcut_failure_does_not_raise_to_application(tmp_path: Path, monkeypatch):
    launcher = tmp_path / "HellsaizLauncher.exe"
    launcher.write_bytes(b"launcher")

    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "powershell.exe", stderr="blocked")

    monkeypatch.setattr(shortcuts.subprocess, "run", fail)

    assert shortcuts.ensure_desktop_shortcut(launcher, is_windows=True) is False


def test_missing_launcher_does_not_call_powershell(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        shortcuts.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    assert shortcuts.ensure_desktop_shortcut(tmp_path / "missing.exe", is_windows=True) is False
