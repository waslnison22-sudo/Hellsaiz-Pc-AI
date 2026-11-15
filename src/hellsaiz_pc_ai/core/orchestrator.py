from __future__ import annotations

import json
from typing import Any, Protocol

from hellsaiz_pc_ai.core.models import ToolResult
from hellsaiz_pc_ai.core.registry import ConfirmCallback, ToolRegistry


MAX_TOOL_CALLS_PER_RESPONSE = 8
MAX_TOOL_CALLS_PER_REPLY = 16
MAX_TOOL_ARGUMENT_JSON_CHARS = 100_000


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON содержит повторяющийся ключ: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON содержит недопустимое числовое значение: {value}")


class ChatProvider(Protocol):
    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]: ...


class AssistantOrchestrator:
    def __init__(
        self, provider: ChatProvider, registry: ToolRegistry, system_prompt: str, max_tool_rounds: int = 4
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_tool_rounds = max(1, min(max_tool_rounds, 8))
        self.history: list[dict[str, Any]] = []

    @staticmethod
    def _parse_tool_calls(raw_calls: Any) -> list[tuple[str, str, dict[str, Any]]]:
        if not isinstance(raw_calls, list):
            raise ValueError("список вызовов инструментов имеет неверный формат")
        if len(raw_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
            raise ValueError(
                f"за один ответ разрешено не более {MAX_TOOL_CALLS_PER_RESPONSE} действий"
            )

        parsed: list[tuple[str, str, dict[str, Any]]] = []
        seen_ids: set[str] = set()
        for index, raw_call in enumerate(raw_calls, start=1):
            if not isinstance(raw_call, dict):
                raise ValueError(f"вызов инструмента #{index} не является объектом")
            call_id = raw_call.get("id")
            if (
                not isinstance(call_id, str)
                or not call_id.strip()
                or len(call_id) > 128
            ):
                raise ValueError(f"вызов инструмента #{index} содержит некорректный id")
            if call_id in seen_ids:
                raise ValueError("модель вернула повторяющийся id вызова инструмента")
            seen_ids.add(call_id)

            function = raw_call.get("function")
            if not isinstance(function, dict):
                raise ValueError(f"вызов инструмента #{index} не содержит function")
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"вызов инструмента #{index} не содержит имя функции")

            raw_arguments = function.get("arguments", "{}")
            if isinstance(raw_arguments, str):
                if len(raw_arguments) > MAX_TOOL_ARGUMENT_JSON_CHARS:
                    raise ValueError(f"аргументы вызова #{index} превышают допустимый размер")
                try:
                    arguments = json.loads(
                        raw_arguments,
                        object_pairs_hook=_strict_json_object,
                        parse_constant=_reject_json_constant,
                    )
                except json.JSONDecodeError as exc:
                    raise ValueError(f"аргументы вызова #{index} не являются корректным JSON") from exc
                except RecursionError as exc:
                    raise ValueError(f"аргументы вызова #{index} имеют чрезмерную вложенность") from exc
            else:
                arguments = raw_arguments
            if not isinstance(arguments, dict):
                raise ValueError(f"аргументы вызова #{index} должны быть JSON-объектом")
            parsed.append((call_id, name, arguments))
        return parsed

    def reply(self, user_text: str, confirm: ConfirmCallback | None = None) -> str:
        user_text = user_text.strip()
        if not user_text:
            return "Напишите сообщение."
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-24:],
            {"role": "user", "content": user_text},
        ]

        executed_tool_calls = 0
        for _ in range(self.max_tool_rounds + 1):
            response = self.provider.complete(messages, self.registry.openai_schemas())
            if not isinstance(response, dict):
                raise RuntimeError("Провайдер вернул ответ в неподдерживаемом формате")
            assistant_message = response.get("message")
            if not isinstance(assistant_message, dict):
                raise RuntimeError("Local model returned an invalid assistant message")
            messages.append(assistant_message)
            raw_calls = assistant_message.get("tool_calls", [])
            if raw_calls is None:
                raw_calls = []
            if raw_calls == []:
                answer = str(assistant_message.get("content") or "Модель вернула пустой ответ.")
                self.history.extend(
                    [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]
                )
                self.history = self.history[-40:]
                return answer

            try:
                calls = self._parse_tool_calls(raw_calls)
            except ValueError as exc:
                return f"Действия не выполнены: {exc}. Повтори запрос более точно."

            if executed_tool_calls + len(calls) > MAX_TOOL_CALLS_PER_REPLY:
                return (
                    f"Действия не выполнены: за один запрос разрешено не более "
                    f"{MAX_TOOL_CALLS_PER_REPLY} вызовов инструментов."
                )

            # Preflight every tool name and argument schema before running any
            # handler, so an invalid later call cannot leave a partial batch.
            for _call_id, name, arguments in calls:
                validation = self.registry.validate_arguments(name, arguments)
                if not validation.ok:
                    return (
                        f"Действия не выполнены: вызов инструмента «{name}» отклонён: "
                        f"{validation.output}. Ни одно действие из пакета не запускалось."
                    )

            for call_id, name, arguments in calls:
                result = self.registry.execute(name, arguments, confirm)
                messages.append(result.as_openai_message(call_id))
            executed_tool_calls += len(calls)

        return "Остановил цепочку инструментов: достигнут лимит последовательных вызовов."
