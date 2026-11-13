from __future__ import annotations

import ctypes
import os
import subprocess
import webbrowser
from urllib.parse import urlparse

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def register_windows_tools(registry: ToolRegistry, allowed_apps: dict[str, tuple[str, ...]]) -> None:
    def open_app(arguments: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Этот инструмент поддерживается только в Windows.")
        alias = str(arguments["app"]).lower()
        command = allowed_apps.get(alias)
        if not command:
            options = ", ".join(sorted(allowed_apps)) or "список пуст"
            return ToolResult(False, f"'{alias}' не разрешено. Доступно: {options}.")
        subprocess.Popen(list(command), shell=False, close_fds=True)
        return ToolResult(True, f"Запущено приложение: {alias}")

    def open_url(arguments: dict[str, object]) -> ToolResult:
        raw_url = str(arguments["url"]).strip()
        candidate = raw_url if "://" in raw_url else f"https://{raw_url}"
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ToolResult(False, "Разрешены только корректные HTTP/HTTPS-ссылки.")
        if not webbrowser.open(candidate, new=2):
            return ToolResult(False, "Windows не смогла открыть ссылку в браузере.")
        return ToolResult(True, f"Открыта ссылка: {candidate}")

    def lock_pc(_: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Блокировка поддерживается только в Windows.")
        if not ctypes.windll.user32.LockWorkStation():
            return ToolResult(False, "Windows не подтвердила блокировку.")
        return ToolResult(True, "Компьютер заблокирован.")

    registry.register(ToolSpec(
        name="open_app",
        description="Запустить приложение Windows по alias из allowlist. Передавай только alias.",
        parameters={
            "type": "object",
            "properties": {"app": {"type": "string", "minLength": 1}},
            "required": ["app"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=open_app,
    ))
    registry.register(ToolSpec(
        name="open_url",
        description="Открыть HTTP или HTTPS ссылку в браузере по прямому запросу пользователя.",
        parameters={
            "type": "object",
            "properties": {"url": {"type": "string", "minLength": 3, "maxLength": 2048}},
            "required": ["url"],
            "additionalProperties": False,
        },
        risk=RiskLevel.CONFIRM,
        handler=open_url,
    ))
    registry.register(ToolSpec(
        name="lock_pc",
        description="Заблокировать текущую сессию Windows.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.CONFIRM,
        handler=lock_pc,
    ))
