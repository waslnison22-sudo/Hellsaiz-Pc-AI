from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult

ConfirmCallback = Callable[["ToolSpec", dict[str, Any]], bool]

MAX_ARGUMENT_DEPTH = 16
MAX_COLLECTION_ITEMS = 1024
MAX_ARGUMENT_STRING_LENGTH = 100_000


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
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Strict argument validation before side effects; actions run without modal approval prompts."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        if not spec.name.replace("_", "").isalnum():
            raise ValueError(f"Invalid tool name: {spec.name}")
        if spec.parameters.get("type") != "object":
            raise ValueError("Tool arguments schema must have type='object'.")
        self._tools[spec.name] = spec

    def get_spec(self, name: str) -> ToolSpec | None:
        """Return immutable tool metadata for host-side permission checks."""
        return self._tools.get(name)

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [spec.as_openai_tool() for spec in self._tools.values()]

    @classmethod
    def _validate_value(
        cls,
        value: Any,
        schema: dict[str, Any],
        path: str,
        depth: int = 0,
    ) -> None:
        if depth > MAX_ARGUMENT_DEPTH:
            raise ValueError(f"{path} exceeds the maximum nesting depth ({MAX_ARGUMENT_DEPTH}).")
        if isinstance(value, str) and len(value) > MAX_ARGUMENT_STRING_LENGTH:
            raise ValueError(
                f"{path} exceeds the maximum string length ({MAX_ARGUMENT_STRING_LENGTH})."
            )
        if isinstance(value, (dict, list)) and len(value) > MAX_COLLECTION_ITEMS:
            raise ValueError(
                f"{path} exceeds the maximum collection size ({MAX_COLLECTION_ITEMS})."
            )

        expected = schema.get("type")
        type_checks = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "null": lambda item: item is None,
        }
        if expected is not None:
            predicate = type_checks.get(expected)
            if predicate is None:
                raise ValueError(f"{path} uses unsupported schema type '{expected}'.")
            if not predicate(value):
                raise ValueError(f"{path} must be {expected}.")

        if "enum" in schema and value not in schema["enum"]:
            raise ValueError(f"{path} must be one of the allowed values.")

        if isinstance(value, str):
            if len(value) < schema.get("minLength", 0):
                raise ValueError(f"{path} is shorter than minLength.")
            if len(value) > schema.get("maxLength", float("inf")):
                raise ValueError(f"{path} is longer than maxLength.")
            pattern = schema.get("pattern")
            if pattern is not None and re.fullmatch(pattern, value) is None:
                raise ValueError(f"{path} does not match the required pattern.")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError(f"{path} must be a finite number.")
            if value < schema.get("minimum", float("-inf")):
                raise ValueError(f"{path} is below the minimum.")
            if value > schema.get("maximum", float("inf")):
                raise ValueError(f"{path} is above the maximum.")

        if isinstance(value, dict):
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            if not isinstance(properties, dict) or not isinstance(required, list):
                raise ValueError(f"{path} has an invalid object schema.")
            missing = [key for key in required if key not in value]
            if missing:
                raise ValueError(f"{path} is missing required fields: {', '.join(missing)}.")
            if schema.get("additionalProperties", False) is False:
                unknown = [key for key in value if key not in properties]
                if unknown:
                    raise ValueError(f"{path} contains unknown fields: {', '.join(unknown)}.")
            for key, item in value.items():
                child_schema = properties.get(key)
                if child_schema is None:
                    continue
                if not isinstance(child_schema, dict):
                    raise ValueError(f"{path}.{key} has an invalid schema.")
                cls._validate_value(item, child_schema, f"{path}.{key}", depth + 1)

        if isinstance(value, list):
            if len(value) < schema.get("minItems", 0):
                raise ValueError(f"{path} has too few items.")
            if len(value) > schema.get("maxItems", float("inf")):
                raise ValueError(f"{path} has too many items.")
            item_schema = schema.get("items")
            if item_schema is not None:
                for index, item in enumerate(value):
                    cls._validate_value(item, item_schema, f"{path}[{index}]", depth + 1)

    def validate_arguments(self, name: str, arguments: Any) -> ToolResult:
        """Validate a tool call without invoking its handler or causing side effects."""
        spec = self._tools.get(name)
        if spec is None:
            return ToolResult(False, f"Инструмент '{name}' не зарегистрирован.")
        if not isinstance(arguments, dict):
            return ToolResult(False, "Аргументы инструмента должны быть JSON-объектом.")
        try:
            self._validate_value(arguments, spec.parameters, "arguments")
        except ValueError as exc:
            return ToolResult(False, f"Аргументы отклонены: {exc}")
        return ToolResult(True, "Аргументы допустимы.")

    def execute(
        self, name: str, arguments: dict[str, Any], confirm: ConfirmCallback | None = None
    ) -> ToolResult:
        validation = self.validate_arguments(name, arguments)
        if not validation.ok:
            return validation
        spec = self._tools[name]
        if confirm is not None:
            try:
                accepted = bool(confirm(spec, arguments))
            except Exception as exc:
                return ToolResult(
                    False,
                    f"Не удалось получить подтверждение действия: {type(exc).__name__}: {exc}",
                )
            if not accepted:
                return ToolResult(False, "Действие отменено пользователем.")
        # Confirmation only adds a user decision. Registered-tool allowlists and
        # the argument schema above remain mandatory for every policy.
        try:
            return spec.handler(arguments)
        except Exception as exc:
            return ToolResult(False, f"Ошибка инструмента ({type(exc).__name__}): {exc}")
