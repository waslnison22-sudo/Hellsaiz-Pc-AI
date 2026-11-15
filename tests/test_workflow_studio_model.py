import pytest

from hellsaiz_pc_ai.workflows.studio_model import (
    build_workflow_graph,
    count_workflow_actions,
    describe_action,
    describe_trigger,
    workflow_to_draft,
)


def test_build_text_scenario_without_exposing_technical_ids():
    graph = build_workflow_graph(
        name="Тихий режим",
        trigger_kind="text",
        trigger_config={"phrases": ["тихий режим", "сделай потише"]},
        actions=[
            {"kind": "tool", "name": "set_volume", "arguments": {"percent": 20}},
            {"kind": "wait", "seconds": 1},
        ],
    )

    assert graph.name == "Тихий режим"
    assert graph.nodes[0].kind == "trigger.text"
    assert graph.nodes[0].config["phrases"] == ["тихий режим", "сделай потише"]
    assert graph.nodes[1].id == "action_01"
    assert describe_trigger(graph).startswith("Фраза:")
    assert describe_action(graph.nodes[1]) == "Громкость: 20%"
    assert count_workflow_actions(graph) == 2


def test_build_schedule_scenario_with_selected_weekdays():
    graph = build_workflow_graph(
        name="Рабочее утро",
        trigger_kind="schedule",
        trigger_config={"time": "08:30", "days": [1, 2, 3, 4, 5]},
        actions=[{"kind": "tool", "name": "set_volume", "arguments": {"percent": 45}}],
    )

    assert graph.nodes[0].config == {"time": "08:30", "days": [1, 2, 3, 4, 5]}
    assert "понедельник" in describe_trigger(graph)
    assert "пятницу" in describe_trigger(graph)


def test_build_condition_with_both_action_branches():
    graph = build_workflow_graph(
        name="Ночной режим",
        trigger_kind="text",
        trigger_config={"phrase": "ночной режим"},
        condition={"kind": "hour", "operator": "gte", "value": 22},
        true_actions=[{"kind": "tool", "name": "set_volume", "arguments": {"percent": 20}}],
        false_actions=[{"kind": "tool", "name": "set_volume", "arguments": {"percent": 50}}],
    )

    condition = next(node for node in graph.nodes if node.kind == "condition.hour")
    branches = [edge for edge in graph.edges if edge.source == condition.id]

    assert {edge.when for edge in branches} == {"true", "false"}
    assert len(branches) == 2
    assert count_workflow_actions(graph) == 2


def test_empty_condition_branches_receive_safe_noop_nodes():
    graph = build_workflow_graph(
        name="День недели",
        trigger_kind="startup",
        trigger_config={},
        condition={"kind": "weekday", "value": 1},
        true_actions=[],
        false_actions=[],
    )

    assert count_workflow_actions(graph) == 2
    assert all(node.kind == "action.wait" for node in graph.nodes if node.kind.startswith("action."))


def test_draft_round_trip_preserves_supported_scenario():
    original = build_workflow_graph(
        name="Игровой режим",
        trigger_kind="text",
        trigger_config={"phrases": ["игровой режим", "включи игры"]},
        condition={"kind": "hour", "operator": "gte", "value": 20},
        true_actions=[{"kind": "tool", "name": "set_volume", "arguments": {"percent": 70}}],
        false_actions=[{"kind": "tool", "name": "set_volume", "arguments": {"percent": 45}}],
    )

    draft = workflow_to_draft(original)
    rebuilt = build_workflow_graph(**draft)

    assert rebuilt == original


def test_draft_reader_preserves_existing_repeat_block():
    graph = build_workflow_graph(
        name="Повтор",
        trigger_kind="text",
        trigger_config={"phrase": "повтори"},
        actions=[{"kind": "repeat", "name": "set_volume", "arguments": {"percent": 40}, "count": 2}],
    )

    draft = workflow_to_draft(graph)

    assert draft["actions"] == [
        {
            "kind": "repeat",
            "name": "set_volume",
            "arguments": {"percent": 40},
            "count": 2,
        }
    ]
    assert build_workflow_graph(**draft) == graph


def test_invalid_trigger_and_empty_linear_scenario_are_rejected():
    with pytest.raises(ValueError, match="способ запуска"):
        build_workflow_graph(
            name="bad",
            trigger_kind="shell",
            trigger_config={},
            actions=[{"kind": "wait", "seconds": 1}],
        )
    with pytest.raises(ValueError, match="хотя бы один"):
        build_workflow_graph(
            name="empty",
            trigger_kind="startup",
            trigger_config={},
            actions=[],
        )


def test_nested_condition_cannot_be_silently_edited_as_simple_blocks():
    from hellsaiz_pc_ai.workflows.graph import WorkflowGraph

    graph = WorkflowGraph.from_dict({
        "name": "Вложенное условие",
        "nodes": [
            {"id": "start", "type": "trigger.text", "config": {"phrase": "проверка"}},
            {"id": "hour", "type": "condition.hour", "config": {"operator": "gte", "value": 22}},
            {"id": "weekday", "type": "condition.weekday", "config": {"value": 1}},
            {"id": "night", "type": "action.wait", "config": {"seconds": 1}},
            {"id": "late", "type": "action.wait", "config": {"seconds": 2}},
            {"id": "day", "type": "action.wait", "config": {"seconds": 3}},
        ],
        "edges": [
            {"from": "start", "to": "hour"},
            {"from": "hour", "to": "weekday", "when": "true"},
            {"from": "hour", "to": "day", "when": "false"},
            {"from": "weekday", "to": "night", "when": "true"},
            {"from": "weekday", "to": "late", "when": "false"},
        ],
    })

    with pytest.raises(ValueError, match="сложный блок"):
        workflow_to_draft(graph)
