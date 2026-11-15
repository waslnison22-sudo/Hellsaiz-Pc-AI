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


def make_action_assistant(provider):
    calls = []
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "perform", "test",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE,
        lambda _args: (calls.append("performed") or ToolResult(True, "ok")),
    ))
    return AssistantOrchestrator(provider, registry, "system"), calls


class OneBatchProvider:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls

    def complete(self, messages, tools):
        return {"message": {"role": "assistant", "tool_calls": self.tool_calls}}


def _tool_call(call_id):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "perform", "arguments": "{}"},
    }


def test_orchestrator_rejects_more_than_eight_calls_without_side_effects():
    assistant, calls = make_action_assistant(
        OneBatchProvider([_tool_call(f"call_{index}") for index in range(9)])
    )

    result = assistant.reply("выполни действия")

    assert "не более 8 действий" in result
    assert calls == []


def test_orchestrator_validates_the_entire_batch_before_execution():
    malformed = _tool_call("call_2")
    malformed["function"]["arguments"] = "{invalid"
    assistant, calls = make_action_assistant(
        OneBatchProvider([_tool_call("call_1"), malformed])
    )

    result = assistant.reply("выполни действия")

    assert "некорректным JSON" in result
    assert calls == []


def test_orchestrator_rejects_duplicate_tool_call_ids():
    assistant, calls = make_action_assistant(
        OneBatchProvider([_tool_call("duplicate"), _tool_call("duplicate")])
    )

    result = assistant.reply("выполни действия")

    assert "повторяющийся id" in result
    assert calls == []


def test_orchestrator_limits_total_tool_calls_across_rounds():
    class TwoBatchProvider:
        def __init__(self):
            self.round = 0

        def complete(self, messages, tools):
            self.round += 1
            if self.round <= 2:
                batch = [_tool_call(f"call_{self.round}_{index}") for index in range(8)]
            else:
                batch = [_tool_call("call_after_limit")]
            return {"message": {"role": "assistant", "tool_calls": batch}}

    assistant, calls = make_action_assistant(TwoBatchProvider())

    result = assistant.reply("выполни действия")

    assert "не более 16 вызовов" in result
    assert len(calls) == 16

