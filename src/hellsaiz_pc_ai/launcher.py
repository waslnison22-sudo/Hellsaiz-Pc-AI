from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _show_error(message: str) -> None:
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Hellsaiz PC AI", 0x10)


def main() -> int:
    root = Path(sys.executable).resolve().parent
    try:
        active = json.loads((root / "active.json").read_text(encoding="utf-8"))
        if not isinstance(active, dict):
            raise ValueError("Файл active.json имеет неверный формат.")
        version = active.get("active_version")
        if not isinstance(version, str) or not version:
            raise ValueError("В active.json отсутствует active_version.")
        target = (root / "versions" / version / "HellsaizPC_AI.exe").resolve()
        versions = (root / "versions").resolve()
        if target.parent.parent != versions or not target.is_file():
            raise ValueError("Файлы установленной версии не найдены.")
        subprocess.Popen(
            [str(target), *sys.argv[1:]],
            cwd=str(target.parent),
            close_fds=True,
        )
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        _show_error(
            f"Не удалось запустить Hellsaiz PC AI.\n\n{exc}\n\n"
            "Запустите установщик ещё раз или восстановите приложение."
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
