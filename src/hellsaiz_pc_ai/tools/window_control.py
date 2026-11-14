from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
WM_CLOSE = 0x0010


def _load_user32():
    if os.name != "nt":
        raise OSError("Управление окнами поддерживается только в Windows.")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindow.argtypes = (wintypes.HWND,)
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindowAsync.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindowAsync.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.PostMessageW.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.EnumWindows.argtypes = (ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    return user32


def _read_title(user32: Any, hwnd: Any) -> str:
    length = max(0, int(user32.GetWindowTextLengthW(hwnd)))
    buffer = ctypes.create_unicode_buffer(length + 1)
    if length:
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value.strip()


def _window_process(user32: Any, hwnd: Any) -> tuple[int, str]:
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    pid = int(process_id.value)
    process_name = f"PID {pid}"
    try:
        import psutil

        process_name = psutil.Process(pid).name()
    except (ImportError, OSError, ValueError):
        pass
    except Exception:
        # AccessDenied and NoSuchProcess are normal races while windows close.
        pass
    return pid, process_name


def _enumerate_windows(user32: Any) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []

    def collect(hwnd: Any, _lparam: Any) -> bool:
        try:
            if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
                return True
            title = _read_title(user32, hwnd)
            if not title:
                return True
            pid, process_name = _window_process(user32, hwnd)
            windows.append({
                "hwnd": hwnd,
                "title": title,
                "pid": pid,
                "process": process_name,
            })
        except Exception:
            # A window can disappear during enumeration; keep scanning others.
            return True
        return True

    callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    callback = callback_type(collect)
    if not user32.EnumWindows(callback, 0):
        raise OSError("Windows не смогла перечислить открытые окна.")
    return windows


def _format_windows(windows: list[dict[str, Any]]) -> str:
    if not windows:
        return "Не найдено видимых окон с заголовками."
    return "\n".join(
        f"{index}. {item['title']} — {item['process']} (PID {item['pid']})"
        for index, item in enumerate(windows, start=1)
    )


def _list_windows() -> ToolResult:
    try:
        windows = _enumerate_windows(_load_user32())
        return ToolResult(True, _format_windows(windows))
    except OSError as exc:
        return ToolResult(False, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Не удалось получить список окон ({type(exc).__name__}): {exc}")


def _focus_window(target: str) -> ToolResult:
    query = " ".join(target.casefold().split())
    if not query:
        return ToolResult(False, "Укажи название окна.")
    try:
        user32 = _load_user32()
        windows = _enumerate_windows(user32)
        matches = [
            item for item in windows
            if query in item["title"].casefold()
            or query in item["process"].casefold()
        ]
        if not matches:
            return ToolResult(False, f"Не найдено открытое окно по запросу «{target}».")
        if len(matches) > 1:
            return ToolResult(
                False,
                "Нашлось несколько окон. Уточни заголовок: "
                + "; ".join(item["title"] for item in matches[:8]),
            )
        item = matches[0]
        hwnd = item["hwnd"]
        if user32.IsIconic(hwnd):
            user32.ShowWindowAsync(hwnd, SW_RESTORE)
        if not user32.SetForegroundWindow(hwnd):
            return ToolResult(
                False,
                f"Windows не разрешила переключиться на окно «{item['title']}».",
            )
        return ToolResult(True, f"Активировано окно «{item['title']}» ({item['process']}).")
    except OSError as exc:
        return ToolResult(False, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Не удалось переключить окно ({type(exc).__name__}): {exc}")


def _foreground_window(user32: Any):
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindow(hwnd):
        return None, ""
    return hwnd, _read_title(user32, hwnd)


def _window_action(action: str, command: int | None = None) -> ToolResult:
    try:
        user32 = _load_user32()
        hwnd, title = _foreground_window(user32)
        if hwnd is None:
            return ToolResult(False, "Не найдено активное окно Windows.")
        label = f" «{title}»" if title else ""
        if action == "close":
            if not user32.PostMessageW(hwnd, WM_CLOSE, 0, 0):
                return ToolResult(False, f"Windows не приняла запрос на закрытие окна{label}.")
            return ToolResult(True, f"Отправлен штатный запрос на закрытие окна{label}.")
        if command is None or not user32.ShowWindowAsync(hwnd, command):
            if not user32.IsWindow(hwnd):
                return ToolResult(False, "Активное окно больше не существует.")
        messages = {
            "minimize": "Окно свёрнуто",
            "maximize": "Окно развёрнуто",
            "restore": "Окно восстановлено",
        }
        return ToolResult(True, f"{messages[action]}{label}.")
    except OSError as exc:
        return ToolResult(False, str(exc))
    except Exception as exc:
        return ToolResult(False, f"Ошибка управления окном ({type(exc).__name__}): {exc}")


def register_window_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="list_windows",
        description="Показать видимые окна Windows с заголовками и именами процессов.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.CONFIRM,
        handler=lambda _arguments: _list_windows(),
    ))
    registry.register(ToolSpec(
        name="focus_window",
        description="Переключиться на единственное открытое окно по части его заголовка или имени процесса. При неоднозначности ничего не переключать.",
        parameters={
            "type": "object",
            "properties": {"target": {"type": "string", "minLength": 1, "maxLength": 160}},
            "required": ["target"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda arguments: _focus_window(str(arguments["target"])),
    ))
    operations = (
        ("minimize_active_window", "Свернуть активное окно Windows.", "minimize", SW_MINIMIZE),
        ("maximize_active_window", "Развернуть активное окно Windows.", "maximize", SW_MAXIMIZE),
        ("restore_active_window", "Восстановить активное окно Windows.", "restore", SW_RESTORE),
        ("close_active_window", "Штатно закрыть активное окно через WM_CLOSE.", "close", None),
    )
    for name, description, action, command in operations:
        registry.register(ToolSpec(
            name=name,
            description=description,
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            risk=RiskLevel.CONFIRM,
            handler=lambda _arguments, action=action, command=command: _window_action(
                action, command
            ),
        ))
