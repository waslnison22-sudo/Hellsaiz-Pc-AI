from __future__ import annotations

import json
from typing import Any, Protocol

from hellsaiz_pc_ai.core.models import ToolResult
from hellsaiz_pc_ai.core.registry import ConfirmCallback, ToolRegistry


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

    def reply(self, user_text: str, confirm: ConfirmCallback | None = None) -> str:
        user_text = user_text.strip()
        if not user_text:
            return "Напишите сообщение."
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            *self.history[-24:],
            {"role": "user", "content": user_text},
        ]

        for _ in range(self.max_tool_rounds + 1):
            response = self.provider.complete(messages, self.registry.openai_schemas())
            assistant_message = response.get("message")
            if not isinstance(assistant_message, dict):
                raise RuntimeError("Local model returned an invalid assistant message")
            messages.append(assistant_message)
            calls = assistant_message.get("tool_calls") or []
            if not calls:
                answer = str(assistant_message.get("content") or "Модель вернула пустой ответ.")
                self.history.extend(
                    [{"role": "user", "content": user_text}, {"role": "assistant", "content": answer}]
                )
                self.history = self.history[-40:]
                return answer

            for raw_call in calls:
                call_id = str(raw_call.get("id", "invalid_call")) if isinstance(raw_call, dict) else "invalid_call"
                try:
                    function = raw_call["function"]
                    name = function["name"]
                    raw_arguments = function.get("arguments", "{}")
                    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    result = self.registry.execute(str(name), arguments, confirm)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    result = ToolResult(False, f"Некорректный вызов инструмента: {exc}")
                messages.append(result.as_openai_message(call_id))

        return "Остановил цепочку инструментов: достигнут лимит последовательных вызовов."
