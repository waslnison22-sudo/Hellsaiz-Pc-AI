from __future__ import annotations

import json
import sys
from pathlib import Path


def installed_app_root(executable: str | Path | None = None) -> Path | None:
    if not getattr(sys, "frozen", False) and executable is None:
        return None
    exe = Path(executable or sys.executable).resolve()
    version_dir = exe.parent
    versions_dir = version_dir.parent
    if versions_dir.name.casefold() != "versions":
        return None
    root = versions_dir.parent
    active_file = root / "active.json"
    if not active_file.is_file():
        return None
    return root


def installed_version(root: Path | None, fallback: str = "0.1.0") -> str:
    if root is None:
        return fallback
    try:
        data = json.loads((root / "active.json").read_text(encoding="utf-8"))
        version = data.get("active_version")
        if isinstance(version, str) and version:
            return version
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return fallback


def version_directory(root: Path, version: str) -> Path:
    candidate = (root / "versions" / version).resolve()
    versions_root = (root / "versions").resolve()
    if candidate.parent != versions_root:
        raise ValueError("Версия выходит за пределы каталога приложения.")
    return candidate
