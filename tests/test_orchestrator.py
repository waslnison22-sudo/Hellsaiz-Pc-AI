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


def test_orchestrator_rejects_non_standard_and_ambiguous_json_before_execution():
    malformed_arguments = (
        '{"level": NaN}',
        '{"level": 1, "level": 2}',
        '[]',
    )
    for index, arguments in enumerate(malformed_arguments):
        call = _tool_call(f"invalid_{index}")
        call["function"]["arguments"] = arguments
        assistant, calls = make_action_assistant(OneBatchProvider([call]))

        result = assistant.reply("выполни действия")

        assert "Действия не выполнены" in result
        assert calls == []


def test_orchestrator_rejects_oversized_argument_json_before_execution():
    call = _tool_call("oversized")
    call["function"]["arguments"] = '{"value":"' + ("x" * 100_001) + '"}'
    assistant, calls = make_action_assistant(OneBatchProvider([call]))

    result = assistant.reply("выполни действия")

    assert "превышают допустимый размер" in result
    assert calls == []


def test_orchestrator_preflights_all_tool_schemas_before_any_handler():
    calls = []
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "perform", "test",
        {
            "type": "object",
            "properties": {"value": {"type": "integer", "minimum": 0}},
            "required": ["value"],
            "additionalProperties": False,
        },
        RiskLevel.SAFE,
        lambda args: (calls.append(args["value"]) or ToolResult(True, "ok")),
    ))
    batch = [
        {
            "id": "valid_first",
            "type": "function",
            "function": {"name": "perform", "arguments": '{"value": 1}'},
        },
        {
            "id": "invalid_second",
            "type": "function",
            "function": {"name": "perform", "arguments": '{"unexpected": 2}'},
        },
    ]
    assistant = AssistantOrchestrator(OneBatchProvider(batch), registry, "system")

    result = assistant.reply("выполни пакет")

    assert "Ни одно действие из пакета не запускалось" in result
    assert calls == []

