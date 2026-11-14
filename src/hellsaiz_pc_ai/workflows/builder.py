from __future__ import annotations

from hellsaiz_pc_ai.workflows.graph import WorkflowGraph


def terminal_nodes(graph: WorkflowGraph) -> list[str]:
    sources = {edge.source for edge in graph.edges}
    return [node.id for node in graph.nodes if node.id not in sources and not node.kind.startswith("trigger.")]


def _append_node(
    graph: WorkflowGraph,
    source_id: str,
    new_nodes: list[dict[str, object]],
    new_edges: list[dict[str, str]],
) -> WorkflowGraph:
    if source_id not in terminal_nodes(graph):
        raise ValueError("Choose a terminal node (a branch end) as the insertion point.")
    data = graph.to_dict()
    existing = {node["id"] for node in data["nodes"]}
    new_ids = [node["id"] for node in new_nodes]
    if len(set(new_ids)) != len(new_ids) or any(node_id in existing for node_id in new_ids):
        raise ValueError("A node with this id already exists.")
    if len(data["nodes"]) + len(new_nodes) > 64:
        raise ValueError("Workflow graphs are limited to 64 nodes.")
    data["nodes"].extend(new_nodes)
    data["edges"].extend(new_edges)
    return WorkflowGraph.from_dict(data)


def append_tool_action(
    graph: WorkflowGraph,
    source_id: str,
    node_id: str,
    tool_name: str,
    arguments: dict[str, object],
    registered_tools: set[str],
) -> WorkflowGraph:
    if tool_name not in registered_tools:
        raise ValueError(f"Tool '{tool_name}' is not registered in the host.")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    return _append_node(
        graph, source_id,
        [{"id": node_id, "type": "action.tool", "config": {"name": tool_name, "arguments": arguments}}],
        [{"from": source_id, "to": node_id}],
    )


def append_wait_action(
    graph: WorkflowGraph, source_id: str, node_id: str, seconds: float
) -> WorkflowGraph:
    return _append_node(
        graph, source_id,
        [{"id": node_id, "type": "action.wait", "config": {"seconds": seconds}}],
        [{"from": source_id, "to": node_id}],
    )


def append_hour_condition(
    graph: WorkflowGraph, source_id: str, condition_id: str, operator: str, hour: int
) -> WorkflowGraph:
    true_id, false_id = f"{condition_id}_true", f"{condition_id}_false"
    return _append_node(
        graph, source_id,
        [
            {"id": condition_id, "type": "condition.hour", "config": {"operator": operator, "value": hour}},
            {"id": true_id, "type": "action.wait", "config": {"seconds": 0}},
            {"id": false_id, "type": "action.wait", "config": {"seconds": 0}},
        ],
        [
            {"from": source_id, "to": condition_id},
            {"from": condition_id, "to": true_id, "when": "true"},
            {"from": condition_id, "to": false_id, "when": "false"},
        ],
    )



def append_repeat_action(
    graph: WorkflowGraph,
    source_id: str,
    node_id: str,
    tool_name: str,
    arguments: dict[str, object],
    count: int,
    registered_tools: set[str],
) -> WorkflowGraph:
    if tool_name not in registered_tools:
        raise ValueError(f"Tool '{tool_name}' is not registered in the host.")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
        raise ValueError("Repeat count must be an integer between 1 and 10.")
    return _append_node(
        graph,
        source_id,
        [{
            "id": node_id,
            "type": "action.repeat",
            "config": {"name": tool_name, "arguments": arguments, "count": count},
        }],
        [{"from": source_id, "to": node_id}],
    )
