from __future__ import annotations

import platform
from datetime import datetime

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def register_system_tools(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="get_local_time",
        description="Получить локальные дату и время компьютера.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.SAFE,
        handler=lambda _: ToolResult(True, datetime.now().astimezone().strftime("%d.%m.%Y %H:%M:%S %Z")),
    ))
    registry.register(ToolSpec(
        name="get_system_info",
        description="Получить базовые сведения об ОС и версии Python.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        risk=RiskLevel.SAFE,
        handler=lambda _: ToolResult(True, f"{platform.system()} {platform.release()} | {platform.machine()} | Python {platform.python_version()}",
            {"system": platform.system(), "release": platform.release(), "machine": platform.machine()}),
    ))
