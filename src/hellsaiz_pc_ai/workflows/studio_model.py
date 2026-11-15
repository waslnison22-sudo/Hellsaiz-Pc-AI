from __future__ import annotations

from typing import Any

from hellsaiz_pc_ai.workflows.graph import GraphEdge, GraphNode, WorkflowGraph


TRIGGER_LABELS = {
    "text": "По голосовой фразе",
    "hotkey": "По сочетанию клавиш",
    "schedule": "По расписанию",
    "startup": "При запуске приложения",
}
ACTION_LABELS = {
    "set_volume": "Изменить громкость",
    "open_app": "Открыть приложение",
    "open_url": "Открыть сайт",
    "lock_pc": "Заблокировать компьютер",
    "close_process": "Закрыть приложение",
    "get_local_time": "Узнать текущее время",
    "get_system_info": "Показать сведения о компьютере",
}
WEEKDAY_LABELS = {
    1: "понедельник",
    2: "вторник",
    3: "среду",
    4: "четверг",
    5: "пятницу",
    6: "субботу",
    7: "воскресенье",
}


def _action_node(node_id: str, action: dict[str, Any]) -> GraphNode:
    kind = action.get("kind")
    if kind == "wait":
        return GraphNode(
            node_id,
            "action.wait",
            {"seconds": action.get("seconds", 1)},
        )
    if kind == "tool":
        return GraphNode(
            node_id,
            "action.tool",
            {
                "name": action.get("name", ""),
                "arguments": action.get("arguments", {}),
            },
        )
    if kind == "repeat":
        return GraphNode(
            node_id,
            "action.repeat",
            {
                "name": action.get("name", ""),
                "arguments": action.get("arguments", {}),
                "count": action.get("count", 1),
            },
        )
    raise ValueError("Неизвестный тип блока действия.")


def build_workflow_graph(
    *,
    name: str,
    trigger_kind: str,
    trigger_config: dict[str, Any],
    actions: list[dict[str, Any]] | None = None,
    condition: dict[str, Any] | None = None,
    true_actions: list[dict[str, Any]] | None = None,
    false_actions: list[dict[str, Any]] | None = None,
) -> WorkflowGraph:
    """Build the existing validated graph format from friendly editor values."""
    if trigger_kind not in TRIGGER_LABELS:
        raise ValueError("Выбран неизвестный способ запуска сценария.")

    trigger = GraphNode(
        "start",
        f"trigger.{trigger_kind}",
        dict(trigger_config),
    )
    nodes: list[GraphNode] = [trigger]
    edges: list[GraphEdge] = []

    def append_chain(
        branch_name: str,
        source_id: str,
        action_list: list[dict[str, Any]],
    ) -> None:
        if not action_list:
            action_list = [{"kind": "wait", "seconds": 0}]
        previous = source_id
        for index, action in enumerate(action_list, start=1):
            node_id = f"{branch_name}_{index:02d}"
            node = _action_node(node_id, action)
            nodes.append(node)
            edges.append(GraphEdge(previous, node_id))
            previous = node_id

    if condition is None:
        action_list = actions or []
        if not action_list:
            raise ValueError("Добавь хотя бы один блок действия.")
        append_chain("action", "start", action_list)
    else:
        condition_kind = condition.get("kind")
        condition_id = "condition"
        if condition_kind == "hour":
            condition_node = GraphNode(
                condition_id,
                "condition.hour",
                {
                    "operator": condition.get("operator", "gte"),
                    "value": condition.get("value", 22),
                },
            )
        elif condition_kind == "weekday":
            condition_node = GraphNode(
                condition_id,
                "condition.weekday",
                {"value": condition.get("value", 1)},
            )
        else:
            raise ValueError("Выбрано неизвестное условие.")
        nodes.append(condition_node)
        edges.append(GraphEdge("start", condition_id))
        append_chain("true", condition_id, true_actions or [])
        append_chain("false", condition_id, false_actions or [])
        # The first node in each branch needs an explicit true/false edge.
        true_first = next(node for node in nodes if node.id == "true_01")
        false_first = next(node for node in nodes if node.id == "false_01")
        edges = [edge for edge in edges if edge.source != condition_id]
        edges.extend([
            GraphEdge(condition_id, true_first.id, "true"),
            GraphEdge(condition_id, false_first.id, "false"),
        ])

    data = {
        "name": name.strip(),
        "nodes": [
            {"id": node.id, "type": node.kind, "config": node.config}
            for node in nodes
        ],
        "edges": [
            {
                "from": edge.source,
                "to": edge.target,
                **({"when": edge.when} if edge.when else {}),
            }
            for edge in edges
        ],
    }
    return WorkflowGraph.from_dict(data)


def _node_map(graph: WorkflowGraph) -> dict[str, GraphNode]:
    return {node.id: node for node in graph.nodes}


def _outgoing(graph: WorkflowGraph) -> dict[str, list[GraphEdge]]:
    result = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        result[edge.source].append(edge)
    return result


def _read_action_chain(
    first_id: str,
    nodes: dict[str, GraphNode],
    outgoing: dict[str, list[GraphEdge]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    current_id = first_id
    while current_id:
        node = nodes[current_id]
        if node.kind == "action.tool":
            actions.append({
                "kind": "tool",
                "name": node.config["name"],
                "arguments": dict(node.config.get("arguments", {})),
            })
        elif node.kind == "action.wait":
            actions.append({
                "kind": "wait",
                "seconds": node.config["seconds"],
            })
        elif node.kind == "action.repeat":
            # Preserve the repeat block as one editable action. Expanding it
            # into N tool nodes loses the user's original repeat setting.
            actions.append({
                "kind": "repeat",
                "name": node.config["name"],
                "arguments": dict(node.config["arguments"]),
                "count": node.config["count"],
            })
        else:
            raise ValueError(
                "В этом сценарии есть сложный блок. Его можно запускать и просматривать, "
                "но пока нельзя изменить в простом редакторе."
            )
        next_edges = outgoing[current_id]
        if len(next_edges) > 1:
            raise ValueError("Вложенные условия пока нельзя изменить в простом редакторе.")
        current_id = next_edges[0].target if next_edges else ""
    return actions


def workflow_to_draft(graph: WorkflowGraph) -> dict[str, Any]:
    """Convert supported saved graphs to editable values without exposing node IDs."""
    nodes = _node_map(graph)
    outgoing = _outgoing(graph)
    root = next(node for node in graph.nodes if node.kind.startswith("trigger."))
    trigger_kind = root.kind.removeprefix("trigger.")
    trigger_config = dict(root.config)
    first_edge = outgoing[root.id][0]
    first_id = first_edge.target
    condition = None
    actions: list[dict[str, Any]] = []
    true_actions: list[dict[str, Any]] = []
    false_actions: list[dict[str, Any]] = []

    if nodes[first_id].kind in {"condition.hour", "condition.weekday"}:
        condition_node = nodes[first_id]
        condition = {"kind": condition_node.kind.removeprefix("condition.")}
        condition.update(condition_node.config)
        branches = {
            edge.when: edge.target
            for edge in outgoing[condition_node.id]
        }
        true_actions = _read_action_chain(branches["true"], nodes, outgoing)
        false_actions = _read_action_chain(branches["false"], nodes, outgoing)
    else:
        actions = _read_action_chain(first_id, nodes, outgoing)

    return {
        "name": graph.name,
        "trigger_kind": trigger_kind,
        "trigger_config": trigger_config,
        "actions": actions,
        "condition": condition,
        "true_actions": true_actions,
        "false_actions": false_actions,
    }


def describe_trigger(graph: WorkflowGraph) -> str:
    root = next(node for node in graph.nodes if node.kind.startswith("trigger."))
    kind = root.kind.removeprefix("trigger.")
    if kind == "text":
        phrases = root.config.get("phrases", [root.config.get("phrase", "")])
        return "Фраза: " + " · ".join(str(item) for item in phrases[:3])
    if kind == "hotkey":
        return f"Клавиши: {root.config.get('hotkey', '')}"
    if kind == "schedule":
        days = root.config.get("days", [])
        day_names = [WEEKDAY_LABELS.get(day, "") for day in days]
        return f"Расписание: {root.config.get('time', '')}, " + ", ".join(day_names)
    return TRIGGER_LABELS[kind]


def describe_action(node: GraphNode) -> str:
    if node.kind == "action.wait":
        return f"Пауза: {node.config.get('seconds', 0):g} сек."
    if node.kind == "action.repeat":
        name = str(node.config.get("name", ""))
        label = ACTION_LABELS.get(name, "действие")
        return f"Повторить: {label.lower()} · {node.config.get('count', 1)} раз"
    if node.kind == "condition.hour":
        operators = {"gte": "не раньше", "gt": "позже", "eq": "ровно", "lte": "не позже", "lt": "раньше"}
        return f"Если час {operators[node.config['operator']]} {node.config['value']}:00"
    if node.kind == "condition.weekday":
        return f"Если сегодня {WEEKDAY_LABELS.get(node.config['value'], 'указанный день')}"
    if node.kind.startswith("trigger."):
        return TRIGGER_LABELS.get(node.kind.removeprefix("trigger."), "Запуск")
    name = str(node.config.get("name", ""))
    label = ACTION_LABELS.get(name, "Действие")
    arguments = node.config.get("arguments", {})
    if name == "set_volume":
        return f"Громкость: {arguments.get('percent', 0)}%"
    if name == "open_app":
        return f"Открыть: {str(arguments.get('app', '')).replace('_', ' ').title()}"
    if name == "open_url":
        return f"Открыть сайт: {arguments.get('url', '')}"
    if name == "close_process":
        return f"Закрыть: {arguments.get('process', '')}"
    if name == "lock_pc":
        return "Заблокировать компьютер"
    return label


def count_workflow_actions(graph: WorkflowGraph) -> int:
    return sum(
        node.kind in {"action.tool", "action.wait", "action.repeat"}
        for node in graph.nodes
    )
