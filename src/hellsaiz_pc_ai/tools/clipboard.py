from __future__ import annotations

import ctypes
import os

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
MAX_CLIPBOARD_CHARS = 50_000
MAX_WRITE_CHARS = 20_000


def _windows_libraries():
    if os.name != "nt":
        raise OSError("Буфер обмена поддерживается только в Windows.")

    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = (wintypes.HWND,)
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = ()
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = ()
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = (wintypes.UINT,)
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = (wintypes.UINT,)
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
    user32.SetClipboardData.restype = wintypes.HANDLE

    kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalSize.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    return user32, kernel32


def _last_error(message: str) -> OSError:
    error_code = ctypes.get_last_error()
    if error_code:
        return ctypes.WinError(error_code, message)
    return OSError(message)


def read_clipboard_text() -> str:
    """Read only CF_UNICODETEXT after an explicit user request."""
    user32, kernel32 = _windows_libraries()
    if not user32.OpenClipboard(None):
        raise _last_error("Не удалось открыть буфер обмена.")

    handle = None
    pointer = None
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            raise _last_error("Не удалось получить текст из буфера обмена.")

        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise _last_error("Не удалось прочитать данные буфера обмена.")

        size_bytes = int(kernel32.GlobalSize(handle))
        char_size = ctypes.sizeof(ctypes.c_wchar)
        if size_bytes < char_size:
            return ""
        char_count = size_bytes // char_size
        if char_count > MAX_CLIPBOARD_CHARS + 1:
            raise ValueError(
                f"Текст в буфере превышает лимит {MAX_CLIPBOARD_CHARS} символов."
            )

        value = ctypes.wstring_at(pointer, char_count)
        return value.split("\x00", 1)[0]
    finally:
        if pointer:
            kernel32.GlobalUnlock(handle)
        user32.CloseClipboard()


def write_clipboard_text(text: str) -> None:
    """Replace CF_UNICODETEXT using movable global memory owned by Windows."""
    if not isinstance(text, str):
        raise TypeError("В буфер обмена можно скопировать только текст.")
    if not text:
        raise ValueError("Нельзя скопировать пустой текст.")
    if "\x00" in text:
        raise ValueError("Текст содержит недопустимый нулевой символ.")
    if len(text) > MAX_WRITE_CHARS:
        raise ValueError(f"Лимит текста для копирования — {MAX_WRITE_CHARS} символов.")

    user32, kernel32 = _windows_libraries()
    encoded = (text + "\x00").encode("utf-16-le")
    memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not memory:
        raise _last_error("Не удалось выделить память для буфера обмена.")

    transferred = False
    pointer = kernel32.GlobalLock(memory)
    if not pointer:
        kernel32.GlobalFree(memory)
        raise _last_error("Не удалось подготовить память для буфера обмена.")

    try:
        ctypes.memmove(pointer, encoded, len(encoded))
    finally:
        kernel32.GlobalUnlock(memory)

    clipboard_open = False
    try:
        if not user32.OpenClipboard(None):
            raise _last_error("Не удалось открыть буфер обмена.")
        clipboard_open = True

        if not user32.EmptyClipboard():
            raise _last_error("Не удалось очистить буфер обмена.")
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            raise _last_error("Windows не приняла текст буфера обмена.")
        transferred = True
    finally:
        if clipboard_open:
            user32.CloseClipboard()
        if not transferred:
            kernel32.GlobalFree(memory)


def register_clipboard_tools(registry) -> None:
    from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
    from hellsaiz_pc_ai.core.registry import ToolSpec

    def read_handler(_: dict[str, object]) -> ToolResult:
        try:
            value = read_clipboard_text()
        except (OSError, ValueError) as exc:
            return ToolResult(False, str(exc))
        if value == "":
            return ToolResult(False, "В буфере обмена нет текстовых данных.")
        return ToolResult(True, value, {"characters": len(value)})

    def write_handler(arguments: dict[str, object]) -> ToolResult:
        text = str(arguments["text"])
        try:
            write_clipboard_text(text)
        except (OSError, ValueError, TypeError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, f"Текст скопирован в буфер обмена ({len(text)} символов).")

    registry.register(
        ToolSpec(
            name="read_clipboard",
            description="Прочитать текст Windows clipboard только по прямому запросу пользователя.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk=RiskLevel.SAFE,
            handler=read_handler,
        )
    )
    registry.register(
        ToolSpec(
            name="write_clipboard",
            description="Скопировать переданный текст в Windows clipboard после подтверждения пользователя.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_WRITE_CHARS,
                    }
                },
                "required": ["text"],
                "additionalProperties": False,
            },
            risk=RiskLevel.CONFIRM,
            handler=write_handler,
        )
    )
