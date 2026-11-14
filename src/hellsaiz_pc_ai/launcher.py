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


def resolve_active_target(install_root: Path) -> Path:
    """Resolve the selected version while preventing path traversal outside versions/."""
    install_root = Path(install_root).resolve()
    active = json.loads((install_root / "active.json").read_text(encoding="utf-8"))
    if not isinstance(active, dict) or active.get("schema_version") != 1:
        raise ValueError("Файл active.json имеет неподдерживаемую схему.")
    version = active.get("active_version")
    if (
        not isinstance(version, str)
        or not version
        or version in {".", ".."}
        or Path(version).name != version
        or "/" in version
        or "\\" in version
    ):
        raise ValueError("В active.json указана недопустимая версия.")
    versions_root = (install_root / "versions").resolve()
    unresolved_target = install_root / "versions" / version / "HellsaizPC_AI.exe"
    if unresolved_target.is_symlink():
        raise ValueError("Файл приложения не должен быть символической ссылкой.")
    target = unresolved_target.resolve()
    if target.parent.parent != versions_root or not target.is_file():
        raise ValueError("Файлы установленной версии не найдены.")
    return target


def main() -> int:
    root = Path(sys.executable).resolve().parent
    try:
        target = resolve_active_target(root)
        if sys.argv[1:] == ["--self-test"]:
            return 0
        subprocess.Popen(
            [str(target), *sys.argv[1:]],
            cwd=str(target.parent),
            close_fds=True,
        )
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        _show_error(
            f"Не удалось запустить Hellsaiz PC AI.\\n\\n{exc}\\n\\n"
            "Запустите установщик ещё раз или восстановите приложение."
        )
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
