from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.workflows.runner import Workflow, WorkflowRunner


def test_workflow_runs_only_registered_tools():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "ping", "test", {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE, lambda _: ToolResult(True, "pong")
    ))
    workflow = Workflow.from_dict({"name": "health", "steps": [{"tool": "ping"}]})
    result = WorkflowRunner(registry).run(workflow)
    assert result[0].ok and result[0].output == "pong"


def test_workflow_rejects_more_than_32_steps():
    try:
        Workflow.from_dict({"name": "too-many", "steps": [{"tool": "x"}] * 33})
    except ValueError as exc:
        assert "32" in str(exc)
    else:
        raise AssertionError("Workflow limit was not enforced")


def test_workflow_rejects_code_fields():
    try:
        Workflow.from_dict({"name": "bad", "steps": [], "python": "print(1)"})
    except ValueError:
        return
    raise AssertionError("Unexpected workflow field was accepted")
