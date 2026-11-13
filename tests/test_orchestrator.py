from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.orchestrator import AssistantOrchestrator
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


class FakeProvider:
    def __init__(self):
        self.round = 0

    def complete(self, messages, tools):
        self.round += 1
        if self.round == 1:
            return {"message": {"role": "assistant", "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "check", "arguments": "{}"}
            }]}}
        assert any(message.get("role") == "tool" for message in messages)
        return {"message": {"role": "assistant", "content": "Готово"}}


def test_tool_roundtrip():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "check", "test", {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE, lambda _: ToolResult(True, "ok")
    ))
    assistant = AssistantOrchestrator(FakeProvider(), registry, "system")
    assert assistant.reply("проверка") == "Готово"
    assert assistant.history[-1]["content"] == "Готово"
