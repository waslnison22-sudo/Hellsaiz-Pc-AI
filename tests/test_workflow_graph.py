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
    with pytest.raises(ValueError):
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


def make_trigger_graph(kind, config):
    return WorkflowGraph.from_dict({
        "name": "Trigger test",
        "nodes": [
            {"id": "start", "type": kind, "config": config},
            {"id": "done", "type": "action.wait", "config": {"seconds": 0}},
        ],
        "edges": [{"from": "start", "to": "done"}],
    })


def test_schedule_trigger_validates_time_and_weekdays():
    valid = make_trigger_graph(
        "trigger.schedule", {"time": "07:45", "days": [1, 2, 3, 4, 5]}
    )
    assert valid.nodes[0].config["time"] == "07:45"

    with pytest.raises(ValueError, match="HH:MM"):
        make_trigger_graph("trigger.schedule", {"time": "25:00", "days": [1]})
    with pytest.raises(ValueError, match="weekdays"):
        make_trigger_graph("trigger.schedule", {"time": "07:45", "days": [1, 1]})


def test_startup_trigger_rejects_config():
    with pytest.raises(ValueError, match="does not accept configuration"):
        make_trigger_graph("trigger.startup", {"delay": 1})


def test_runner_accepts_startup_and_schedule_events():
    startup = make_trigger_graph("trigger.startup", {})
    schedule = make_trigger_graph(
        "trigger.schedule", {"time": "07:45", "days": [1, 2, 3, 4, 5, 6, 7]}
    )
    startup_result = WorkflowGraphRunner(registry()).run(
        startup, WorkflowTrigger("startup", "")
    )
    schedule_result = WorkflowGraphRunner(registry()).run(
        schedule, WorkflowTrigger("schedule", "07:45")
    )
    assert startup_result.started and startup_result.completed
    assert schedule_result.started and schedule_result.completed



def test_repeat_action_executes_registered_tool_exactly_n_times():
    data = {
        "name": "Repeat",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "repeat"}},
            {
                "id": "repeat",
                "type": "action.repeat",
                "config": {
                    "name": "set_volume",
                    "arguments": {"percent": 35},
                    "count": 3,
                },
            },
        ],
        "edges": [{"from": "start", "to": "repeat"}],
    }
    graph = WorkflowGraph.from_dict(data)
    result = WorkflowGraphRunner(registry()).run(
        graph, WorkflowTrigger("text", "repeat"), confirm=allow
    )

    assert result.completed
    assert [step.output for step in result.steps] == ["Volume 35"] * 3


def test_repeat_action_stops_when_a_confirmation_is_rejected():
    data = {
        "name": "Repeat",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "repeat"}},
            {
                "id": "repeat",
                "type": "action.repeat",
                "config": {
                    "name": "set_volume",
                    "arguments": {"percent": 35},
                    "count": 4,
                },
            },
        ],
        "edges": [{"from": "start", "to": "repeat"}],
    }
    decisions = iter([True, False, True, True])
    result = WorkflowGraphRunner(registry()).run(
        WorkflowGraph.from_dict(data),
        WorkflowTrigger("text", "repeat"),
        confirm=lambda *_: next(decisions),
    )

    assert result.started and not result.completed
    assert len(result.steps) == 2
    assert "повтор 2/4" in result.message.casefold()


@pytest.mark.parametrize("count", [0, 11, True, 1.5])
def test_repeat_action_rejects_unbounded_or_invalid_counts(count):
    data = {
        "name": "Repeat",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "repeat"}},
            {
                "id": "repeat",
                "type": "action.repeat",
                "config": {"name": "set_volume", "arguments": {"percent": 20}, "count": count},
            },
        ],
        "edges": [{"from": "start", "to": "repeat"}],
    }
    with pytest.raises(ValueError, match="1..10"):
        WorkflowGraph.from_dict(data)



def test_weekday_condition_executes_the_matching_branch():
    graph = WorkflowGraph.from_dict({
        "name": "Weekday",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "weekday"}},
            {"id": "day", "type": "condition.weekday", "config": {"value": 6}},
            {"id": "saturday", "type": "action.wait", "config": {"seconds": 0}},
            {"id": "other", "type": "action.wait", "config": {"seconds": 1}},
        ],
        "edges": [
            {"from": "start", "to": "day"},
            {"from": "day", "to": "saturday", "when": "true"},
            {"from": "day", "to": "other", "when": "false"},
        ],
    })
    runner = WorkflowGraphRunner(registry(), clock=lambda: datetime(2026, 11, 14, 10, 0))
    result = runner.run(graph, WorkflowTrigger("text", "weekday"))

    assert result.completed
    assert "Ожидание 0 сек." in result.steps[0].output


def test_weekday_condition_rejects_invalid_values():
    for value in (0, 8, True, 2.5):
        with pytest.raises(ValueError, match="ISO weekday"):
            WorkflowGraph.from_dict({
                "name": "Invalid weekday",
                "nodes": [
                    {"id": "start", "type": "trigger.text", "config": {"phrase": "go"}},
                    {"id": "day", "type": "condition.weekday", "config": {"value": value}},
                    {"id": "yes", "type": "action.wait", "config": {"seconds": 0}},
                    {"id": "no", "type": "action.wait", "config": {"seconds": 0}},
                ],
                "edges": [
                    {"from": "start", "to": "day"},
                    {"from": "day", "to": "yes", "when": "true"},
                    {"from": "day", "to": "no", "when": "false"},
                ],
            })



def test_text_trigger_accepts_multiple_alias_phrases():
    graph = WorkflowGraph.from_dict({
        "name": "Gaming",
        "nodes": [
            {
                "id": "start",
                "type": "trigger.text",
                "config": {"phrases": ["игровой режим", "открой игры", "запусти стим"]},
            },
            {"id": "end", "type": "action.wait", "config": {"seconds": 0}},
        ],
        "edges": [{"from": "start", "to": "end"}],
    })
    runner = WorkflowGraphRunner(registry())

    for phrase in ("игровой режим", "открой игры", "запусти стим"):
        result = runner.run(graph, WorkflowTrigger("text", phrase))
        assert result.started and result.completed


def test_text_trigger_rejects_duplicate_or_oversized_alias_lists():
    for phrases in ([], ["same", "same"], ["x" * 129], ["one"] * 17):
        with pytest.raises(ValueError, match="phrases|duplicate"):
            WorkflowGraph.from_dict({
                "name": "Invalid text trigger",
                "nodes": [
                    {"id": "start", "type": "trigger.text", "config": {"phrases": phrases}},
                    {"id": "end", "type": "action.wait", "config": {"seconds": 0}},
                ],
                "edges": [{"from": "start", "to": "end"}],
            })


def test_text_trigger_does_not_accept_phrase_and_phrases_together():
    with pytest.raises(ValueError, match="phrase or phrases"):
        WorkflowGraph.from_dict({
            "name": "Invalid trigger schema",
            "nodes": [
                {
                    "id": "start",
                    "type": "trigger.text",
                    "config": {"phrase": "start", "phrases": ["start", "go"]},
                },
                {"id": "end", "type": "action.wait", "config": {"seconds": 0}},
            ],
            "edges": [{"from": "start", "to": "end"}],
        })



def test_graph_rejects_non_string_node_types_without_type_error():
    data = build_graph().to_dict()
    data["nodes"][0]["type"] = []
    with pytest.raises(ValueError, match="Unsupported node type"):
        WorkflowGraph.from_dict(data)


def test_graph_rejects_unhashable_edge_branches_without_type_error():
    data = build_graph().to_dict()
    data["edges"][2]["when"] = []
    with pytest.raises(ValueError, match="Edge branch"):
        WorkflowGraph.from_dict(data)


def test_graph_rejects_unhashable_hour_operators_without_type_error():
    data = build_graph().to_dict()
    data["nodes"][2]["config"]["operator"] = []
    with pytest.raises(ValueError, match="Hour condition"):
        WorkflowGraph.from_dict(data)
