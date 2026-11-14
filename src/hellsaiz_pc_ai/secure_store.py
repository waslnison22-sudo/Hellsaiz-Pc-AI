from __future__ import annotations

import base64
import os
from pathlib import Path


class SecureStoreError(RuntimeError):
    pass


def protect_text(value: str) -> bytes:
    if os.name != "nt":
        raise SecureStoreError("Защищённое хранилище доступно только в Windows.")
    if not value:
        return b""
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    raw = value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    destination = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DataBlob), wintypes.LPCWSTR, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptProtectData(
        ctypes.byref(source), "Hellsaiz PC AI update credential", None,
        None, None, 0, ctypes.byref(destination)
    ):
        raise SecureStoreError(f"Windows DPAPI не смогла защитить ключ (код {ctypes.get_last_error()}).")
    try:
        protected = ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(destination.pbData, ctypes.c_void_p))
    return protected


def unprotect_text(value: bytes) -> str:
    if os.name != "nt":
        raise SecureStoreError("Защищённое хранилище доступно только в Windows.")
    if not value:
        return ""
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(value)
    source = DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    destination = DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.POINTER(DataBlob),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(destination)
    ):
        raise SecureStoreError(f"Windows DPAPI не смогла расшифровать ключ (код {ctypes.get_last_error()}).")
    try:
        raw = ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(destination.pbData, ctypes.c_void_p))
    return raw.decode("utf-8")


def save_secret(path: Path, value: str) -> None:
    if not value.strip():
        delete_secret(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = protect_text(value.strip())
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(base64.b64encode(protected).decode("ascii"), encoding="ascii")
    temporary.replace(path)


def load_secret(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        protected = base64.b64decode(path.read_text(encoding="ascii"), validate=True)
        return unprotect_text(protected)
    except (OSError, ValueError, UnicodeError) as exc:
        raise SecureStoreError(f"Не удалось прочитать защищённый ключ: {exc}") from exc


def delete_secret(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise SecureStoreError(f"Не удалось удалить защищённый ключ: {exc}") from exc
