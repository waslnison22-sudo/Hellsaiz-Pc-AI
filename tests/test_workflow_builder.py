import pytest

from hellsaiz_pc_ai.workflows.builder import append_hour_condition, append_repeat_action, append_tool_action, append_wait_action, append_weekday_condition, terminal_nodes
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



def test_append_repeat_action_uses_registered_tool_and_is_bounded():
    updated = append_repeat_action(
        sample_graph(), "end", "repeat-volume", "set_volume",
        {"percent": 25}, 3, {"set_volume"},
    )
    node = next(node for node in updated.nodes if node.id == "repeat-volume")
    assert node.kind == "action.repeat"
    assert node.config["count"] == 3
    assert terminal_nodes(updated) == ["repeat-volume"]


def test_append_repeat_action_rejects_unregistered_tool_and_unbounded_count():
    with pytest.raises(ValueError, match="not registered"):
        append_repeat_action(sample_graph(), "end", "repeat", "powershell", {}, 2, set())
    with pytest.raises(ValueError, match="1 and 10"):
        append_repeat_action(sample_graph(), "end", "repeat", "set_volume", {}, 99, {"set_volume"})



def test_append_weekday_condition_creates_two_branches():
    updated = append_weekday_condition(sample_graph(), "end", "weekday", 6)
    assert {edge.when for edge in updated.edges if edge.source == "weekday"} == {"true", "false"}
    assert set(terminal_nodes(updated)) == {"weekday_true", "weekday_false"}


def test_append_weekday_condition_rejects_invalid_day():
    with pytest.raises(ValueError, match="ISO weekday"):
        append_weekday_condition(sample_graph(), "end", "weekday", 8)
