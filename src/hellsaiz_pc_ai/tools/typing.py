"""Глобальная печать текста в активное окно Windows.

SendInput с флагом KEYEVENTF_UNICODE позволяет печатать любые символы,
включая кириллицу, независимо от текущей раскладки. Лимит 500 символов
и риск-уровень CONFIRM защищают от случайного ввода.
"""
from __future__ import annotations

import os
import time

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec

TYPE_TEXT_MAX = 500


def _type_text_globally(text: str) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "Глобальная печать поддерживается только в Windows.")
    if not text.strip():
        return ToolResult(False, "Пустой текст печатать нечего.")
    if len(text) > TYPE_TEXT_MAX:
        return ToolResult(
            False,
            f"Текст длиннее {TYPE_TEXT_MAX} символов. Раздели его на части.",
        )
    import ctypes

    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_KEYUP = 0x0002
    INPUT_KEYBOARD = 1

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", ctypes.c_ushort),
            ("wScan", ctypes.c_ushort),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("padding", ctypes.c_ubyte * 32)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]

    def build_input(wchar: int, release: bool) -> _INPUT:
        item = _INPUT()
        item.type = INPUT_KEYBOARD
        item.union.ki.wVk = 0
        item.union.ki.wScan = wchar
        item.union.ki.dwFlags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if release else 0)
        return item

    units = text.encode("utf-16-le")
    if len(units) % 2:
        units = units + b"\x00"
    user32 = ctypes.windll.user32
    sent = 0
    batch: list[_INPUT] = []

    def flush() -> int:
        if not batch:
            return 0
        array = (_INPUT * len(batch))(*batch)
        result = int(user32.SendInput(len(batch), array, ctypes.sizeof(_INPUT)))
        batch.clear()
        return result

    for index in range(0, len(units), 2):
        code = units[index] | (units[index + 1] << 8)
        if code == 0:
            continue
        batch.append(build_input(code, False))
        batch.append(build_input(code, True))
        if len(batch) >= 20:
            sent += flush()
            time.sleep(0.01)
    sent += flush()
    if sent == 0:
        return ToolResult(False, "Windows не приняла ввод клавиатуры.")
    return ToolResult(True, f"Напечатано {len(text)} символов в активное окно.")


def register_typing_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="type_text_global",
        description=(
            "Напечатать текст (до 500 символов) в активное окно как с клавиатуры. "
            "Использовать только по явной просьбе пользователя."
        ),
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 500}},
            "required": ["text"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=lambda args: _type_text_globally(str(args["text"])),
    ))
