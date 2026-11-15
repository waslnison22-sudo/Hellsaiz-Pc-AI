"""Голосовое управление VPN-клиентом v2RayTun.

Путь к EXE хранится в network.json рядом с остальными настройками приложения.
Инструменты читают файл при каждом вызове, поэтому изменения из настроек
применяются сразу, без перезапуска.
"""
from __future__ import annotations

import os
from pathlib import Path

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.network.v2raytun import (
    NetworkDependencyError,
    build_network_status,
    detect_v2raytun_running,
    launch_v2raytun,
    load_network_settings,
    validate_executable_path,
)


def register_vpn_tools(registry: ToolRegistry, settings_path: Path) -> None:

    def _load() -> dict[str, object]:
        return load_network_settings(Path(settings_path))

    def start_vpn(_: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Управление VPN поддерживается только в Windows.")
        try:
            net = _load()
        except ValueError as exc:
            return ToolResult(False, f"Сетевые настройки повреждены: {exc}")
        executable = str(net["executable_path"]).strip()
        if not executable:
            return ToolResult(
                False,
                "Укажите путь к v2RayTun в настройках сети приложения.",
            )
        try:
            validate_executable_path(executable)
        except ValueError:
            return ToolResult(
                False,
                "Выбранный EXE v2RayTun не найден. Укажите путь в настройках сети.",
            )
        if detect_v2raytun_running():
            return ToolResult(True, "VPN уже запущен.")
        try:
            launch_v2raytun(executable)
        except NetworkDependencyError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            "VPN запущен. Если туннель не подключён, включите его в окне клиента.",
        )

    def stop_vpn(_: dict[str, object]) -> ToolResult:
        if os.name != "nt":
            return ToolResult(False, "Управление VPN поддерживается только в Windows.")
        if not detect_v2raytun_running():
            return ToolResult(True, "VPN и так не запущен.")
        try:
            import psutil
        except ImportError:
            return ToolResult(
                False,
                'Не найден модуль psutil. Установите поддержку Windows: pip install -e ".[windows]".',
            )
        closed = 0
        denied = 0
        for process in psutil.process_iter(["name", "pid"]):
            name = str(process.info.get("name") or "").casefold()
            if "v2raytun" not in name:
                continue
            if process.pid in {os.getpid(), os.getppid()}:
                continue
            try:
                process.terminate()
                closed += 1
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                denied += 1
        if closed:
            detail = f"VPN выключен (завершено процессов: {closed})."
            if denied:
                detail += f" Не удалось завершить: {denied}."
            return ToolResult(True, detail)
        return ToolResult(False, "Windows не разрешила завершить процессы v2RayTun.")

    def vpn_status(_: dict[str, object]) -> ToolResult:
        try:
            net = _load()
        except ValueError as exc:
            return ToolResult(False, f"Сетевые настройки повреждены: {exc}")
        status = build_network_status(
            str(net["executable_path"]),
            str(net["proxy_url"]),
            str(net["health_url"]),
            require_proxy=bool(net["require_proxy_for_telegram"]),
        )
        running = status.process_running and status.executable_exists
        return ToolResult(bool(running or status.proxy_healthy), status.detail)

    registry.register(ToolSpec(
        name="start_vpn",
        description="Запустить клиент v2RayTun, если путь к EXE указан в настройках сети.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.SAFE,
        handler=start_vpn,
    ))
    registry.register(ToolSpec(
        name="stop_vpn",
        description="Завершить процессы v2RayTun.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.CONFIRM,
        handler=stop_vpn,
    ))
    registry.register(ToolSpec(
        name="vpn_status",
        description="Проверить запуск v2RayTun и доступность локального прокси.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.SAFE,
        handler=vpn_status,
    ))
