from __future__ import annotations

import os
import subprocess

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
        # Executable and arguments come only from local config, never from the model.
        subprocess.Popen(list(command), shell=False, close_fds=True)
        return ToolResult(True, f"Запущено приложение: {alias}")

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
