from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hellsaiz_pc_ai.tools.file_system import default_allowed_roots


MAX_ALLOWED_ROOTS = 12


@dataclass
class FileAccessSettings:
    roots: list[Path] = field(default_factory=list)
    allow_writes: bool = False


def _normalize_roots(raw_roots: Any) -> list[Path]:
    if not isinstance(raw_roots, list):
        raise ValueError("Список разрешённых папок должен быть массивом.")
    if len(raw_roots) > MAX_ALLOWED_ROOTS:
        raise ValueError(f"Можно разрешить не более {MAX_ALLOWED_ROOTS} папок.")
    roots: list[Path] = []
    for raw in raw_roots:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Путь разрешённой папки должен быть строкой.")
        candidate = Path(raw).expanduser().resolve()
        if not candidate.is_dir():
            continue
        if candidate == Path(candidate.anchor):
            raise ValueError("Нельзя разрешить корень диска целиком.")
        if candidate not in roots:
            roots.append(candidate)
    return roots


def load_file_access_settings(path: Path) -> FileAccessSettings:
    if not path.is_file():
        return FileAccessSettings(list(default_allowed_roots()), False)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось прочитать настройки доступа к файлам: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("Файл доступа к файлам имеет неподдерживаемую схему.")
    allow_writes = raw.get("allow_writes", False)
    if not isinstance(allow_writes, bool):
        raise ValueError("allow_writes должен быть логическим значением.")
    return FileAccessSettings(_normalize_roots(raw.get("roots", [])), allow_writes)


def save_file_access_settings(path: Path, settings: FileAccessSettings) -> None:
    roots = _normalize_roots([str(item) for item in settings.roots])
    if not isinstance(settings.allow_writes, bool):
        raise ValueError("allow_writes должен быть логическим значением.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    payload = {
        "schema_version": 1,
        "roots": [str(item) for item in roots],
        "allow_writes": settings.allow_writes,
    }
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)
    settings.roots[:] = roots
