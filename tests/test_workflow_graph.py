from datetime import datetime

import pytest

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph, WorkflowGraphRunner, WorkflowTrigger


def build_graph():
    return WorkflowGraph.from_dict({
        "name": "Night automation",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "режим ночь"}},
            {"id": "close", "type": "action.tool", "config": {"name": "close_process", "arguments": {"process": "Discord.exe"}}},
            {"id": "hour", "type": "condition.hour", "config": {"operator": "gte", "value": 22}},
            {"id": "night", "type": "action.tool", "config": {"name": "set_volume", "arguments": {"percent": 30}}},
            {"id": "day", "type": "action.tool", "config": {"name": "set_volume", "arguments": {"percent": 60}}},
        ],
        "edges": [
            {"from": "start", "to": "close"},
            {"from": "close", "to": "hour"},
            {"from": "hour", "to": "night", "when": "true"},
            {"from": "hour", "to": "day", "when": "false"},
        ],
    })


def registry():
    result = ToolRegistry()
    result.register(ToolSpec(
        "close_process", "close",
        {"type": "object", "properties": {"process": {"type": "string"}}, "required": ["process"]},
        RiskLevel.CONFIRM, lambda _: ToolResult(True, "Closed Discord"),
    ))
    result.register(ToolSpec(
        "set_volume", "volume",
        {"type": "object", "properties": {"percent": {"type": "integer"}}, "required": ["percent"]},
        RiskLevel.CONFIRM, lambda args: ToolResult(True, f"Volume {args['percent']}"),
    ))
    return result


def allow(*_):
    return True


def test_graph_executes_true_time_branch():
    graph = build_graph()
    runner = WorkflowGraphRunner(registry(), clock=lambda: datetime(2026, 1, 1, 23, 0))
    result = runner.run(graph, WorkflowTrigger("text", " РЕЖИМ   НОЧЬ "), confirm=allow)
    assert result.started and result.completed
    assert [step.output for step in result.steps] == ["Closed Discord", "Volume 30"]


def test_graph_executes_false_time_branch():
    graph = build_graph()
    runner = WorkflowGraphRunner(registry(), clock=lambda: datetime(2026, 1, 1, 14, 0))
    result = runner.run(graph, WorkflowTrigger("text", "режим ночь"), confirm=allow)
    assert result.completed
    assert result.steps[-1].output == "Volume 60"


def test_graph_stops_when_user_rejects_action():
    graph = build_graph()
    runner = WorkflowGraphRunner(registry(), clock=lambda: datetime(2026, 1, 1, 23, 0))
    result = runner.run(graph, WorkflowTrigger("text", "режим ночь"), confirm=lambda *_: False)
    assert result.started and not result.completed
    assert len(result.steps) == 1
    assert "отменено" in result.message.casefold()


def test_graph_rejects_cycle():
    data = build_graph().to_dict()
    data["edges"].append({"from": "night", "to": "close"})
    with pytest.raises(ValueError, match="cycle"):
        WorkflowGraph.from_dict(data)


def test_graph_rejects_unreachable_nodes():
    data = build_graph().to_dict()
    data["nodes"].append({"id": "orphan", "type": "action.wait", "config": {"seconds": 1}})
    with pytest.raises(ValueError, match="reachable"):
        WorkflowGraph.from_dict(data)


def test_graph_rejects_python_or_shell_action():
    data = build_graph().to_dict()
    data["nodes"][1]["type"] = "action.python"
    with pytest.raises(ValueError, match="Unsupported node type"):
        WorkflowGraph.from_dict(data)


def test_graph_roundtrip():
    graph = build_graph()
    assert WorkflowGraph.from_dict(graph.to_dict()) == graph
