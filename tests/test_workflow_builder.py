import pytest

from hellsaiz_pc_ai.workflows.builder import append_hour_condition, append_tool_action, append_wait_action, terminal_nodes
from hellsaiz_pc_ai.workflows.graph import WorkflowGraph


def sample_graph():
    return WorkflowGraph.from_dict({
        "name": "Simple",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "go"}},
            {"id": "end", "type": "action.wait", "config": {"seconds": 1}},
        ],
        "edges": [{"from": "start", "to": "end"}],
    })


def test_append_action_connects_to_selected_terminal():
    updated = append_tool_action(sample_graph(), "end", "open-browser", "open_url",
        {"url": "https://example.com"}, {"open_url"})
    assert updated.edges[-1].source == "end"
    assert terminal_nodes(updated) == ["open-browser"]


def test_append_action_rejects_unknown_tool():
    with pytest.raises(ValueError, match="not registered"):
        append_tool_action(sample_graph(), "end", "unsafe", "powershell", {}, set())


def test_append_action_requires_terminal_source():
    with pytest.raises(ValueError, match="terminal node"):
        append_wait_action(sample_graph(), "start", "pause", 2)


def test_hour_condition_creates_two_branches():
    updated = append_hour_condition(sample_graph(), "end", "hour", "gte", 22)
    assert {edge.when for edge in updated.edges if edge.source == "hour"} == {"true", "false"}
    assert set(terminal_nodes(updated)) == {"hour_true", "hour_false"}


def test_hour_condition_rejects_out_of_range_hour():
    with pytest.raises(ValueError):
        append_hour_condition(sample_graph(), "end", "hour", "gte", 24)
