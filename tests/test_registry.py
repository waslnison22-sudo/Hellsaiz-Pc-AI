from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def make_registry(risk=RiskLevel.CONFIRM):
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "perform_action", "test", {"type": "object", "properties": {}, "additionalProperties": False},
        risk, lambda _: ToolResult(True, "done")
    ))
    return registry


def test_confirmation_required_without_callback():
    result = make_registry().execute("perform_action", {})
    assert not result.ok
    assert "подтверждение" in result.output.lower()


def test_confirmation_allows_action():
    result = make_registry().execute("perform_action", {}, lambda *_: True)
    assert result.ok


def test_unknown_arguments_are_rejected():
    assert not make_registry(RiskLevel.SAFE).execute("perform_action", {"unexpected": 1}).ok


def test_unknown_tool_is_rejected():
    assert not make_registry().execute("unregistered", {}).ok
