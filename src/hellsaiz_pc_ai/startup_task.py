from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any


TASK_NAME = "Hellsaiz PC AI"


class StartupTaskError(RuntimeError):
    pass


Runner = Callable[..., Any]


def _run(
    arguments: Sequence[str],
    runner: Runner,
) -> Any:
    try:
        result = runner(
            list(arguments),
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StartupTaskError(f"Не удалось обратиться к Планировщику заданий: {exc}") from exc
    return result


def is_registered(
    *,
    runner: Runner = subprocess.run,
) -> bool:
    if sys.platform != "win32":
        return False
    result = _run(
        ["schtasks.exe", "/Query", "/TN", TASK_NAME],
        runner,
    )
    return getattr(result, "returncode", 1) == 0


def register_startup_task(
    launcher_path: Path,
    *,
    runner: Runner = subprocess.run,
) -> None:
    if sys.platform != "win32":
        raise StartupTaskError("Автозапуск через Планировщик поддерживается только в Windows.")
    launcher = Path(launcher_path).expanduser().resolve()
    if not launcher.is_file() or launcher.name.casefold() != "hellsaizlauncher.exe":
        raise StartupTaskError("Для автозапуска нужен существующий HellsaizLauncher.exe.")
    # /F makes repeated registration idempotent; the task runs at interactive
    # logon and asks Task Scheduler for the highest run level.
    result = _run(
        [
            "schtasks.exe",
            "/Create",
            "/TN",
            TASK_NAME,
            "/SC",
            "ONLOGON",
            "/TR",
            f'"{launcher}"',
            "/RL",
            "HIGHEST",
            "/F",
        ],
        runner,
    )
    if getattr(result, "returncode", 1) != 0:
        details = str(getattr(result, "stderr", "") or getattr(result, "stdout", "")).strip()
        raise StartupTaskError(
            "Windows не зарегистрировала автозапуск."
            + (f" {details[:600]}" if details else "")
        )


def unregister_startup_task(
    *,
    runner: Runner = subprocess.run,
) -> None:
    if sys.platform != "win32":
        raise StartupTaskError("Автозапуск через Планировщик поддерживается только в Windows.")
    result = _run(
        ["schtasks.exe", "/Delete", "/TN", TASK_NAME, "/F"],
        runner,
    )
    if getattr(result, "returncode", 1) != 0:
        details = str(getattr(result, "stderr", "") or getattr(result, "stdout", "")).strip()
        if "cannot find" in details.casefold() or "не удается найти" in details.casefold():
            return
        raise StartupTaskError(
            "Windows не смогла отключить автозапуск."
            + (f" {details[:600]}" if details else "")
        )
