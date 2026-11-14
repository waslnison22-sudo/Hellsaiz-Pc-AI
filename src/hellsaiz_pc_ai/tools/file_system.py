from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from collections.abc import Callable
from typing import Any

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


MAX_DIRECTORY_ENTRIES = 200
MAX_SEARCH_RESULTS = 40
MAX_SEARCH_FILES = 5000
MAX_READ_BYTES = 1024 * 1024
MAX_WRITE_BYTES = 256 * 1024
MAX_OUTPUT_CHARS = 12000
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".toml", ".ini", ".log", ".yaml", ".yml",
    ".xml", ".html", ".css", ".js", ".ts", ".py", ".ps1", ".sql",
}
BLOCKED_OPEN_EXTENSIONS = {
    ".exe", ".com", ".bat", ".cmd", ".msi", ".msp", ".ps1", ".psm1",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".scr", ".lnk",
    ".url", ".reg", ".hta", ".py", ".pyw", ".pyc", ".jar", ".sh", ".dll", ".sys", ".cpl", ".msc",
}


class FileAccessError(RuntimeError):
    pass


def default_allowed_roots() -> tuple[Path, ...]:
    home = Path.home()
    candidates = (home / "Documents", home / "Desktop", home / "Downloads")
    return tuple(path.resolve() for path in candidates if path.is_dir())


def _valid_roots(roots: tuple[Path, ...] | list[Path]) -> tuple[Path, ...]:
    normalized: list[Path] = []
    for root in roots:
        resolved = Path(root).expanduser().resolve()
        if resolved.is_dir() and resolved not in normalized:
            normalized.append(resolved)
    return tuple(normalized)


def resolve_allowed_path(
    raw_path: str,
    roots: tuple[Path, ...] | list[Path],
    *,
    must_exist: bool = False,
) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip() or len(raw_path) > 2048:
        raise FileAccessError("Укажи путь длиной от 1 до 2048 символов.")
    root_paths = _valid_roots(roots)
    if not root_paths:
        raise FileAccessError("Нет разрешённых папок. Добавь папку в настройках доступа к файлам.")

    candidate = Path(raw_path.strip()).expanduser()
    if candidate.is_absolute():
        choices = [candidate]
    else:
        choices = [root / candidate for root in root_paths]

    for choice in choices:
        try:
            resolved = choice.resolve(strict=must_exist)
        except OSError:
            continue
        if any(resolved == root or root in resolved.parents for root in root_paths):
            if must_exist and not resolved.exists():
                continue
            return resolved
    raise FileAccessError(
        "Путь находится вне разрешённых папок или объект не существует. "
        "Укажи полный путь внутри разрешённой папки."
    )


def _list_directory(raw_path: str, roots: tuple[Path, ...] | list[Path]) -> ToolResult:
    try:
        directory = resolve_allowed_path(raw_path, roots, must_exist=True)
        if not directory.is_dir():
            return ToolResult(False, "Указанный путь не является папкой.")
        entries = []
        for item in sorted(directory.iterdir(), key=lambda path: (not path.is_dir(), path.name.casefold())):
            try:
                if item.is_symlink():
                    continue
                info = item.stat()
                kind = "папка" if stat.S_ISDIR(info.st_mode) else "файл"
                entries.append(f"{item.name} — {kind}" + (f" · {info.st_size} Б" if kind == "файл" else ""))
            except OSError:
                continue
            if len(entries) >= MAX_DIRECTORY_ENTRIES:
                break
        if not entries:
            return ToolResult(True, f"Папка пуста: {directory}")
        return ToolResult(True, f"Содержимое {directory}:\n" + "\n".join(entries))
    except FileAccessError as exc:
        return ToolResult(False, str(exc))
    except OSError as exc:
        return ToolResult(False, f"Не удалось прочитать папку ({type(exc).__name__}).")


def _search_files(
    raw_path: str,
    query: str,
    roots: tuple[Path, ...] | list[Path],
) -> ToolResult:
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 160:
        return ToolResult(False, "Поисковый запрос должен содержать от 1 до 160 символов.")
    try:
        root = resolve_allowed_path(raw_path, roots, must_exist=True)
        if not root.is_dir():
            return ToolResult(False, "Искать можно только внутри папки.")
        needle = query.casefold()
        matches: list[str] = []
        visited = 0
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            try:
                depth = len(current_path.relative_to(root).parts)
            except ValueError:
                directories[:] = []
                continue
            if depth >= 5:
                directories[:] = []
            else:
                directories[:] = [
                    name for name in directories
                    if not name.startswith(".") and not (current_path / name).is_symlink()
                ]
            for name in sorted(directories + filenames, key=str.casefold):
                candidate = current_path / name
                if candidate.is_symlink():
                    continue
                visited += 1
                if needle in name.casefold():
                    matches.append(str(candidate))
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        break
                if visited >= MAX_SEARCH_FILES:
                    break
            if len(matches) >= MAX_SEARCH_RESULTS or visited >= MAX_SEARCH_FILES:
                break
        if not matches:
            return ToolResult(
                True,
                f"Совпадений «{query}» не найдено. Проверено объектов: {visited}.",
            )
        suffix = " (достигнут лимит поиска)" if visited >= MAX_SEARCH_FILES or len(matches) >= MAX_SEARCH_RESULTS else ""
        return ToolResult(
            True,
            f"Найдено {len(matches)} совпадений{suffix}:\n" + "\n".join(matches),
        )
    except FileAccessError as exc:
        return ToolResult(False, str(exc))
    except OSError as exc:
        return ToolResult(False, f"Поиск не выполнен ({type(exc).__name__}).")


def _read_text_file(
    raw_path: str,
    roots: tuple[Path, ...] | list[Path],
) -> ToolResult:
    try:
        path = resolve_allowed_path(raw_path, roots, must_exist=True)
        if not path.is_file() or path.suffix.casefold() not in TEXT_EXTENSIONS:
            return ToolResult(False, "Разрешено читать только обычные текстовые файлы поддерживаемых форматов.")
        if path.stat().st_size > MAX_READ_BYTES:
            return ToolResult(False, f"Размер файла превышает лимит {MAX_READ_BYTES // 1024} КБ.")
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return ToolResult(False, "Файл не является корректным UTF-8 текстом.")
        if len(text) > MAX_OUTPUT_CHARS:
            text = text[:MAX_OUTPUT_CHARS] + "\n… [вывод обрезан]"
        return ToolResult(True, f"Содержимое {path}:\n{text}")
    except FileAccessError as exc:
        return ToolResult(False, str(exc))
    except OSError as exc:
        return ToolResult(False, f"Не удалось прочитать файл ({type(exc).__name__}).")


def _open_path(
    raw_path: str,
    roots: tuple[Path, ...] | list[Path],
    opener: Any | None = None,
) -> ToolResult:
    try:
        path = resolve_allowed_path(raw_path, roots, must_exist=True)
        if not path.exists():
            return ToolResult(False, "Указанный путь не существует.")
        if path.is_file() and path.suffix.casefold() in BLOCKED_OPEN_EXTENSIONS:
            return ToolResult(False, "Запуск исполняемых файлов и скриптов через файловый инструмент запрещён.")
        if opener is None:
            if sys.platform != "win32":
                return ToolResult(False, "Открытие файлов через Проводник поддерживается только в Windows.")
            opener = os.startfile
        opener(str(path))
        return ToolResult(True, f"Открыто: {path}")
    except FileAccessError as exc:
        return ToolResult(False, str(exc))
    except OSError as exc:
        return ToolResult(False, f"Windows не смогла открыть путь ({type(exc).__name__}).")


def _create_directory(
    raw_path: str,
    roots: tuple[Path, ...] | list[Path],
    *,
    allow_writes: bool,
) -> ToolResult:
    if not allow_writes:
        return ToolResult(False, "Создание папок отключено. Включи разрешение на изменения файлов в настройках.")
    try:
        target = resolve_allowed_path(raw_path, roots, must_exist=False)
        if target.exists():
            return ToolResult(False, "Папка или файл с таким путём уже существует.")
        target.mkdir(parents=False, exist_ok=False)
        return ToolResult(True, f"Папка создана: {target}")
    except FileAccessError as exc:
        return ToolResult(False, str(exc))
    except OSError as exc:
        return ToolResult(False, f"Не удалось создать папку ({type(exc).__name__}).")


def _write_text_file(
    raw_path: str,
    text: str,
    roots: tuple[Path, ...] | list[Path],
    *,
    allow_writes: bool,
) -> ToolResult:
    if not allow_writes:
        return ToolResult(False, "Запись файлов отключена. Включи разрешение на изменения файлов в настройках.")
    if len(text.encode("utf-8")) > MAX_WRITE_BYTES:
        return ToolResult(False, f"Размер текста превышает лимит {MAX_WRITE_BYTES // 1024} КБ.")
    try:
        target = resolve_allowed_path(raw_path, roots, must_exist=False)
        if target.suffix.casefold() not in TEXT_EXTENSIONS:
            return ToolResult(False, "Создавать можно только текстовые файлы поддерживаемых форматов.")
        if not target.parent.is_dir():
            return ToolResult(False, "Родительская папка не существует.")
        # Exclusive creation prevents accidental overwrite and avoids a check/write race.
        with target.open("x", encoding="utf-8", newline="") as stream:
            stream.write(text)
        return ToolResult(True, f"Новый текстовый файл создан без перезаписи: {target}")
    except FileExistsError:
        return ToolResult(False, "Файл уже существует. Перезапись через голосовую команду запрещена.")
    except FileAccessError as exc:
        return ToolResult(False, str(exc))
    except OSError as exc:
        return ToolResult(False, f"Не удалось записать файл ({type(exc).__name__}).")


def register_file_system_tools(
    registry: ToolRegistry,
    roots: tuple[Path, ...] | list[Path] | Callable[[], tuple[Path, ...]],
    *,
    allow_writes: bool | Callable[[], bool] = False,
) -> None:
    def current_roots() -> tuple[Path, ...]:
        value = roots() if callable(roots) else roots
        return tuple(Path(item).resolve() for item in value)

    def writes_enabled() -> bool:
        return bool(allow_writes() if callable(allow_writes) else allow_writes)

    registry.register(ToolSpec(
        name="list_directory",
        description="Показать содержимое одной папки внутри разрешённых корней доступа.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 2048}},
            "required": ["path"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _list_directory(str(args["path"]), current_roots()),
    ))
    registry.register(ToolSpec(
        name="search_files",
        description="Найти файлы и папки по части имени внутри одной разрешённой папки.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 2048},
                "query": {"type": "string", "minLength": 1, "maxLength": 160},
            },
            "required": ["path", "query"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _search_files(str(args["path"]), str(args["query"]), current_roots()),
    ))
    registry.register(ToolSpec(
        name="read_text_file",
        description="Прочитать текстовый файл UTF-8 размером не более 1 MiB внутри разрешённых папок.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 2048}},
            "required": ["path"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _read_text_file(str(args["path"]), current_roots()),
    ))
    registry.register(ToolSpec(
        name="open_allowed_path",
        description="Открыть документ или папку внутри разрешённых корней. Не запускает исполняемые файлы.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 2048}},
            "required": ["path"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _open_path(str(args["path"]), current_roots()),
    ))
    registry.register(ToolSpec(
        name="create_directory",
        description="Создать новую папку внутри разрешённого корня только при включённом разрешении на запись.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 2048}},
            "required": ["path"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _create_directory(
            str(args["path"]), current_roots(), allow_writes=writes_enabled()
        ),
    ))
    registry.register(ToolSpec(
        name="write_text_file",
        description="Создать новый текстовый файл UTF-8 без перезаписи существующего файла при включённом разрешении на запись.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 2048},
                "text": {"type": "string", "maxLength": MAX_WRITE_BYTES},
            },
            "required": ["path", "text"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _write_text_file(
            str(args["path"]), str(args["text"]), current_roots(), allow_writes=writes_enabled()
        ),
    ))
