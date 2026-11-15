from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


MAX_CONTROLS = 40
MAX_TEXT_LENGTH = 4000
ALLOWED_SHORTCUTS = {
    "CTRL+A": "^a",
    "CTRL+C": "^c",
    "CTRL+F": "^f",
    "CTRL+L": "^l",
    "CTRL+S": "^s",
    "CTRL+T": "^t",
    "CTRL+V": "^v",
    "ALT+LEFT": "%{LEFT}",
    "ALT+RIGHT": "%{RIGHT}",
    "ESC": "{ESC}",
    "F5": "{F5}",
}


def _desktop():
    if os.name != "nt":
        raise OSError("UI Automation поддерживается только в Windows.")
    try:
        from pywinauto import Desktop
    except ImportError as exc:
        raise OSError(
            'Не установлен модуль pywinauto. Установи поддержку Windows: pip install -e ".[windows]".'
        ) from exc
    return Desktop(backend="uia")


def _window_matches(desktop: Any, title_query: str) -> list[Any]:
    query = " ".join(title_query.casefold().split())
    if not query:
        return []
    matches = []
    for window in desktop.windows(visible_only=True):
        try:
            title = " ".join(str(window.window_text() or "").casefold().split())
            if title and query in title:
                matches.append(window)
        except Exception:
            # A window may close or become inaccessible during enumeration.
            continue
    return matches


def _select_window(desktop: Any, title_query: str) -> tuple[Any | None, str | None]:
    matches = _window_matches(desktop, title_query)
    if not matches:
        return None, f"Не найдено видимое окно по заголовку «{title_query}»."
    if len(matches) > 1:
        titles = []
        for item in matches[:8]:
            try:
                titles.append(str(item.window_text() or "без заголовка"))
            except Exception:
                continue
        return None, "Найдено несколько окон. Уточни заголовок: " + "; ".join(titles)
    return matches[0], None


@dataclass(frozen=True)
class _ControlSnapshot:
    control: Any
    name: str
    control_type: str
    automation_id: str


def _snapshot_controls(window: Any, *, require_interactive: bool = False) -> list[_ControlSnapshot]:
    """Read each control's identifying properties once for this UIA operation."""
    snapshots: list[_ControlSnapshot] = []
    for control in window.descendants():
        try:
            name = str(control.window_text() or "").strip()
            info = control.element_info
            if not name:
                name = str(info.name or "").strip()
            if not name:
                continue
            if require_interactive and (
                not control.is_visible() or not control.is_enabled()
            ):
                continue
            snapshots.append(_ControlSnapshot(
                control=control,
                name=name,
                control_type=str(info.control_type or "Unknown"),
                automation_id=str(info.automation_id or "")[:80],
            ))
        except Exception:
            # UIA providers can disappear while the tree is being enumerated.
            continue
    return snapshots


def _is_actionable(snapshot: _ControlSnapshot) -> bool:
    """Recheck transient state immediately before invoking a UIA side effect."""
    try:
        return bool(snapshot.control.is_visible() and snapshot.control.is_enabled())
    except Exception:
        return False


def _control_matches(window: Any, name_query: str) -> list[_ControlSnapshot]:
    query = " ".join(name_query.casefold().split())
    if not query:
        return []
    snapshots = _snapshot_controls(window, require_interactive=True)
    matches = [
        item for item in snapshots
        if query == " ".join(item.name.casefold().split())
        or query in " ".join(item.name.casefold().split())
    ]
    exact = [
        item for item in matches
        if " ".join(item.name.casefold().split()) == query
    ]
    return exact or matches


def _inspect_window(title_query: str) -> ToolResult:
    try:
        desktop = _desktop()
        window, error = _select_window(desktop, title_query)
        if error:
            return ToolResult(False, error)
        snapshots = _snapshot_controls(window)
        controls = [
            {
                "name": item.name[:160],
                "type": item.control_type,
                "automation_id": item.automation_id,
            }
            for item in snapshots[:MAX_CONTROLS]
        ]
        if not controls:
            return ToolResult(
                False,
                "UI Automation не обнаружила доступных подписанных элементов этого окна.",
            )
        lines = [
            f"{index}. {item['name']} [{item['type']}]"
            + (f" · id={item['automation_id']}" if item["automation_id"] else "")
            for index, item in enumerate(controls, start=1)
        ]
        return ToolResult(
            True,
            f"Элементы окна «{window.window_text()}» (показаны первые {len(controls)}):\n"
            + "\n".join(lines),
        )
    except OSError as exc:
        return ToolResult(False, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Не удалось прочитать UI Automation ({type(exc).__name__}).")


def _click_control(title_query: str, name_query: str) -> ToolResult:
    try:
        desktop = _desktop()
        window, error = _select_window(desktop, title_query)
        if error:
            return ToolResult(False, error)
        matches = _control_matches(window, name_query)
        if not matches:
            return ToolResult(False, f"В окне «{window.window_text()}» не найден элемент «{name_query}».")
        if len(matches) > 1:
            return ToolResult(
                False,
                f"Элемент «{name_query}» неоднозначен: найдено {len(matches)} совпадений. "
                "Уточни название из списка элементов.",
            )
        snapshot = matches[0]
        if not _is_actionable(snapshot):
            return ToolResult(
                False,
                f"Элемент «{snapshot.name}» изменился или стал недоступен. Повтори поиск элементов окна.",
            )
        snapshot.control.click_input()
        return ToolResult(
            True,
            f"Нажат элемент «{snapshot.name}» в окне «{window.window_text()}».",
        )
    except OSError as exc:
        return ToolResult(False, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Windows не выполнила нажатие ({type(exc).__name__}).")


def _send_keyboard_shortcut(title_query: str, shortcut: str) -> ToolResult:
    normalized = "+".join(part.strip().upper() for part in shortcut.split("+"))
    sequence = ALLOWED_SHORTCUTS.get(normalized)
    if sequence is None:
        return ToolResult(
            False,
            "Сочетание не разрешено. Доступны: " + ", ".join(sorted(ALLOWED_SHORTCUTS)) + ".",
        )
    try:
        desktop = _desktop()
        window, error = _select_window(desktop, title_query)
        if error:
            return ToolResult(False, error)
        window.set_focus()
        window.type_keys(sequence, set_foreground=True)
        return ToolResult(
            True,
            f"Сочетание {normalized} отправлено в окно «{window.window_text()}».",
        )
    except OSError as exc:
        return ToolResult(False, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Не удалось отправить сочетание ({type(exc).__name__}).")


def _type_into_control(title_query: str, name_query: str, text: str) -> ToolResult:
    if len(text) > MAX_TEXT_LENGTH:
        return ToolResult(False, f"Текст ограничен {MAX_TEXT_LENGTH} символами.")
    try:
        desktop = _desktop()
        window, error = _select_window(desktop, title_query)
        if error:
            return ToolResult(False, error)
        matches = _control_matches(window, name_query)
        if not matches:
            return ToolResult(False, f"В окне «{window.window_text()}» не найдено поле «{name_query}».")
        if len(matches) > 1:
            return ToolResult(
                False,
                f"Поле «{name_query}» неоднозначно: найдено {len(matches)} совпадений.",
            )
        snapshot = matches[0]
        if snapshot.control_type not in {"Edit", "ComboBox", "Document"}:
            return ToolResult(
                False,
                f"Элемент «{snapshot.name}» не является поддерживаемым полем ввода.",
            )
        if not _is_actionable(snapshot):
            return ToolResult(
                False,
                f"Поле «{snapshot.name}» изменилось или стало недоступно. Повтори поиск элементов окна.",
            )
        control = snapshot.control
        control.set_focus()
        setter = getattr(control, "set_edit_text", None)
        if not callable(setter):
            return ToolResult(False, "UI Automation не предоставляет безопасную операцию установки текста.")
        setter(text)
        return ToolResult(
            True,
            f"Текст введён в поле «{snapshot.name}» окна «{window.window_text()}».",
        )
    except OSError as exc:
        return ToolResult(False, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Windows не смогла заполнить поле ({type(exc).__name__}).")


def register_ui_automation_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="inspect_window_controls",
        description="Показать доступные UI Automation элементы одного видимого окна Windows по заголовку.",
        parameters={
            "type": "object",
            "properties": {"window_title": {"type": "string", "minLength": 1, "maxLength": 160}},
            "required": ["window_title"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _inspect_window(str(args["window_title"])),
    ))
    registry.register(ToolSpec(
        name="click_window_control",
        description="Нажать единственный видимый и активный UI Automation элемент с заданным названием в одном указанном окне.",
        parameters={
            "type": "object",
            "properties": {
                "window_title": {"type": "string", "minLength": 1, "maxLength": 160},
                "control_name": {"type": "string", "minLength": 1, "maxLength": 160},
            },
            "required": ["window_title", "control_name"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _click_control(
            str(args["window_title"]), str(args["control_name"])
        ),
    ))
    registry.register(ToolSpec(
        name="send_keyboard_shortcut",
        description="Отправить одно из разрешённых клавиатурных сочетаний в единственное выбранное окно Windows.",
        parameters={
            "type": "object",
            "properties": {
                "window_title": {"type": "string", "minLength": 1, "maxLength": 160},
                "shortcut": {"type": "string", "enum": sorted(ALLOWED_SHORTCUTS)},
            },
            "required": ["window_title", "shortcut"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _send_keyboard_shortcut(
            str(args["window_title"]), str(args["shortcut"])
        ),
    ))
    registry.register(ToolSpec(
        name="type_into_window_control",
        description="Вставить буквальный текст в единственное UI Automation поле Edit/ComboBox/Document. Не исполняет клавиатурные макросы.",
        parameters={
            "type": "object",
            "properties": {
                "window_title": {"type": "string", "minLength": 1, "maxLength": 160},
                "control_name": {"type": "string", "minLength": 1, "maxLength": 160},
                "text": {"type": "string", "maxLength": MAX_TEXT_LENGTH},
            },
            "required": ["window_title", "control_name", "text"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _type_into_control(
            str(args["window_title"]), str(args["control_name"]), str(args["text"])
        ),
    ))
