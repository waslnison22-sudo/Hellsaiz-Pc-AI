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
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.ShowWindowAsync.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindowAsync.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.PostMessageW.restype = wintypes.BOOL
    return user32


def _foreground_window(user32: Any):
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not user32.IsWindow(hwnd):
        return None, ""
    length = max(0, int(user32.GetWindowTextLengthW(hwnd)))
    buffer = ctypes.create_unicode_buffer(length + 1)
    if length:
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return hwnd, buffer.value.strip()


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
            # ShowWindowAsync can return False when a window was previously
            # hidden; IsWindow above is the authoritative existence check.
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
