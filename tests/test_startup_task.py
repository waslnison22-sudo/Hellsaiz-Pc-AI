from __future__ import annotations

from pathlib import Path

import pytest

from hellsaiz_pc_ai import startup_task


class FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_register_startup_task_uses_launcher_logon_and_highest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(startup_task.sys, "platform", "win32")
    launcher = tmp_path / "HellsaizLauncher.exe"
    launcher.write_bytes(b"launcher")
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        return FakeResult()

    startup_task.register_startup_task(launcher, runner=runner)

    args, kwargs = calls[0]
    assert args[0] == "schtasks.exe"
    assert args[args.index("/SC") + 1] == "ONLOGON"
    assert args[args.index("/RL") + 1] == "HIGHEST"
    assert args[args.index("/TR") + 1] == f'"{launcher.resolve()}"'
    assert args[-1] == "/F"
    assert kwargs["timeout"] == 25
    assert kwargs["check"] is False


def test_register_startup_task_rejects_wrong_launcher(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(startup_task.os, "name", "nt")
    wrong = tmp_path / "HellsaizPC_AI.exe"
    wrong.write_bytes(b"wrong")
    with pytest.raises(startup_task.StartupTaskError, match="HellsaizLauncher.exe"):
        startup_task.register_startup_task(wrong, runner=lambda *_a, **_k: FakeResult())


def test_register_startup_task_reports_scheduler_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(startup_task.os, "name", "nt")
    launcher = tmp_path / "HellsaizLauncher.exe"
    launcher.write_bytes(b"launcher")
    with pytest.raises(startup_task.StartupTaskError, match="не зарегистрировала"):
        startup_task.register_startup_task(
            launcher,
            runner=lambda *_a, **_k: FakeResult(1, stderr="Access is denied"),
        )


def test_unregister_startup_task_is_idempotent_when_missing(monkeypatch):
    monkeypatch.setattr(startup_task.os, "name", "nt")
    startup_task.unregister_startup_task(
        runner=lambda *_a, **_k: FakeResult(1, stderr="ERROR: Cannot find the file specified")
    )


def test_startup_status_uses_schtasks_query(monkeypatch):
    monkeypatch.setattr(startup_task.os, "name", "nt")
    result = startup_task.is_registered(
        runner=lambda *_a, **_k: FakeResult(0)
    )
    assert result is True


def test_non_windows_startup_registration_is_rejected(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(startup_task.sys, "platform", "linux")
    with pytest.raises(startup_task.StartupTaskError):
        startup_task.register_startup_task(tmp_path / "HellsaizLauncher.exe")
