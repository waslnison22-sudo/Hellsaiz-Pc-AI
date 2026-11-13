from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult

ConfirmCallback = Callable[["ToolSpec", dict[str, Any]], bool]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    risk: RiskLevel
    handler: Callable[[dict[str, Any]], ToolResult]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        if not spec.name.replace("_", "").isalnum():
            raise ValueError(f"Invalid tool name: {spec.name}")
        self._tools[spec.name] = spec

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [spec.as_openai_tool() for spec in self._tools.values()]

    def execute(
        self, name: str, arguments: dict[str, Any], confirm: ConfirmCallback | None = None
    ) -> ToolResult:
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(False, f"Инструмент '{name}' не зарегистрирован.")
        if not isinstance(arguments, dict):
            return ToolResult(False, "Аргументы инструмента должны быть JSON-объектом.")
        properties = spec.parameters.get("properties", {})
        required = spec.parameters.get("required", [])
        if any(key not in arguments for key in required):
            return ToolResult(False, "Не переданы обязательные аргументы.")
        if any(key not in properties for key in arguments):
            return ToolResult(False, "Переданы неизвестные аргументы.")
        if spec.risk == RiskLevel.CONFIRM and (confirm is None or not confirm(spec, arguments)):
            return ToolResult(False, "Действие отменено: подтверждение не получено.")
        try:
            return spec.handler(arguments)
        except Exception as exc:
            return ToolResult(False, f"Ошибка инструмента ({type(exc).__name__}): {exc}")
