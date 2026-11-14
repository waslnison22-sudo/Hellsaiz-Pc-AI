from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal

from hellsaiz_pc_ai.core.models import ToolResult
from hellsaiz_pc_ai.core.registry import ConfirmCallback, ToolRegistry

NodeKind = Literal["trigger.text", "trigger.hotkey", "trigger.schedule", "trigger.startup", "condition.hour", "condition.weekday", "action.tool", "action.repeat", "action.wait"]
_ALLOWED_KINDS = {"trigger.text", "trigger.hotkey", "trigger.schedule", "trigger.startup", "condition.hour", "condition.weekday", "action.tool", "action.repeat", "action.wait"}
_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_HOTKEY_RE = re.compile(
    r"^(?:(?:Ctrl|Alt|Shift|Win)\+){1,3}(?:[A-Z0-9]|F(?:[1-9]|1[0-2])|SPACE|ENTER|TAB)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GraphNode:
    id: str
    kind: NodeKind
    config: dict[str, Any]


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    when: Literal["true", "false"] | None = None


@dataclass(frozen=True)
class WorkflowGraph:
    name: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowGraph:
        if not isinstance(data, dict) or set(data) != {"name", "nodes", "edges"}:
            raise ValueError("Workflow graph must contain only name, nodes and edges.")
        name, raw_nodes, raw_edges = data["name"], data["nodes"], data["edges"]
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise ValueError("Workflow name must contain 1..100 characters.")
        if not isinstance(raw_nodes, list) or not 2 <= len(raw_nodes) <= 64:
            raise ValueError("Workflow graph must contain 2..64 nodes.")
        if not isinstance(raw_edges, list) or not 1 <= len(raw_edges) <= 96:
            raise ValueError("Workflow graph must contain 1..96 edges.")

        nodes: list[GraphNode] = []
        by_id: dict[str, GraphNode] = {}
        for item in raw_nodes:
            if not isinstance(item, dict) or set(item) != {"id", "type", "config"}:
                raise ValueError("Every node must contain id, type and config.")
            node_id, kind, config = item["id"], item["type"], item["config"]
            if not isinstance(node_id, str) or not _ID_RE.fullmatch(node_id):
                raise ValueError("Node id must be a short alphanumeric identifier.")
            if node_id in by_id:
                raise ValueError(f"Duplicate node id: {node_id}")
            if kind not in _ALLOWED_KINDS:
                raise ValueError(f"Unsupported node type: {kind}")
            if not isinstance(config, dict):
                raise ValueError(f"Node '{node_id}' config must be an object.")
            node = GraphNode(node_id, kind, config)
            cls._validate_node(node)
            nodes.append(node)
            by_id[node_id] = node

        edges: list[GraphEdge] = []
        seen_edges: set[tuple[str, str, str | None]] = set()
        for item in raw_edges:
            if not isinstance(item, dict) or set(item) - {"from", "to", "when"}:
                raise ValueError("Every edge must contain from, to and optional when.")
            source, target, when = item.get("from"), item.get("to"), item.get("when")
            if not isinstance(source, str) or not isinstance(target, str):
                raise ValueError("Edge endpoints must be node identifiers.")
            if source not in by_id or target not in by_id:
                raise ValueError("An edge references a missing node.")
            if when not in (None, "true", "false"):
                raise ValueError("Edge branch must be true, false or null.")
            if by_id[target].kind.startswith("trigger."):
                raise ValueError("Edges cannot point into trigger nodes.")
            key = (source, target, when)
            if key in seen_edges:
                raise ValueError("Duplicate edge.")
            seen_edges.add(key)
            edges.append(GraphEdge(source, target, when))

        cls._validate_graph(tuple(nodes), tuple(edges))
        return cls(name.strip(), tuple(nodes), tuple(edges))

    @staticmethod
    def _validate_node(node: GraphNode) -> None:
        cfg = node.config
        if node.kind == "trigger.text":
            if set(cfg) == {"phrase"}:
                phrases = [cfg["phrase"]]
            elif set(cfg) == {"phrases"}:
                phrases = cfg["phrases"]
            else:
                raise ValueError(
                    f"Text trigger '{node.id}' needs phrase or phrases, but not both."
                )
            if (
                not isinstance(phrases, list)
                or not 1 <= len(phrases) <= 16
                or any(
                    not isinstance(phrase, str) or not phrase.strip() or len(phrase) > 128
                    for phrase in phrases
                )
            ):
                raise ValueError(f"Text trigger '{node.id}' needs 1..16 phrases (1..128 chars each).")
            normalized_phrases = [re.sub(r"\s+", " ", phrase.casefold()).strip() for phrase in phrases]
            if len(set(normalized_phrases)) != len(normalized_phrases):
                raise ValueError(f"Text trigger '{node.id}' contains duplicate phrases.")
        elif node.kind == "trigger.hotkey":
            hotkey = cfg.get("hotkey")
            if set(cfg) != {"hotkey"} or not isinstance(hotkey, str) or not _HOTKEY_RE.fullmatch(hotkey):
                raise ValueError(f"Hotkey trigger '{node.id}' has an unsupported shortcut.")
        elif node.kind == "trigger.schedule":
            scheduled_time, days = cfg.get("time"), cfg.get("days")
            if set(cfg) != {"time", "days"}:
                raise ValueError(f"Schedule trigger '{node.id}' needs only time and days.")
            if not isinstance(scheduled_time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", scheduled_time):
                raise ValueError(f"Schedule trigger '{node.id}' time must use HH:MM.")
            if (
                not isinstance(days, list)
                or not days
                or any(isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 7 for day in days)
                or len(set(days)) != len(days)
            ):
                raise ValueError(f"Schedule trigger '{node.id}' days must be unique ISO weekdays 1..7.")
        elif node.kind == "trigger.startup":
            if cfg:
                raise ValueError(f"Startup trigger '{node.id}' does not accept configuration.")
        elif node.kind == "condition.hour":
            operator, value = cfg.get("operator"), cfg.get("value")
            if set(cfg) != {"operator", "value"} or operator not in {"eq", "lt", "lte", "gt", "gte"}:
                raise ValueError(f"Hour condition '{node.id}' has invalid settings.")
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 23:
                raise ValueError(f"Hour condition '{node.id}' value must be 0..23.")
        elif node.kind == "condition.weekday":
            weekday = cfg.get("value")
            if (
                set(cfg) != {"value"}
                or isinstance(weekday, bool)
                or not isinstance(weekday, int)
                or not 1 <= weekday <= 7
            ):
                raise ValueError(f"Weekday condition '{node.id}' value must be ISO weekday 1..7.")
        elif node.kind == "action.tool":
            tool, arguments = cfg.get("name"), cfg.get("arguments", {})
            if set(cfg) - {"name", "arguments"} or not isinstance(tool, str) or not tool:
                raise ValueError(f"Tool action '{node.id}' needs a registered tool name.")
            if not isinstance(arguments, dict):
                raise ValueError(f"Tool action '{node.id}' arguments must be an object.")
        elif node.kind == "action.repeat":
            tool, arguments, count = cfg.get("name"), cfg.get("arguments"), cfg.get("count")
            if set(cfg) != {"name", "arguments", "count"}:
                raise ValueError(f"Repeat action '{node.id}' needs name, arguments and count.")
            if not isinstance(tool, str) or not tool.strip() or not isinstance(arguments, dict):
                raise ValueError(f"Repeat action '{node.id}' needs a registered tool and JSON arguments.")
            if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10:
                raise ValueError("A repeat action is limited to 1..10 iterations.")
        elif node.kind == "action.wait":
            seconds = cfg.get("seconds")
            if set(cfg) != {"seconds"} or isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
                raise ValueError(f"Wait action '{node.id}' needs a numeric seconds value.")
            if not 0 <= seconds <= 30:
                raise ValueError("A workflow wait is limited to 0..30 seconds.")

    @staticmethod
    def _validate_graph(nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...]) -> None:
        by_id = {node.id: node for node in nodes}
        triggers = [node for node in nodes if node.kind.startswith("trigger.")]
        if len(triggers) != 1:
            raise ValueError("A workflow must have exactly one trigger node.")

        outgoing: dict[str, list[GraphEdge]] = {node.id: [] for node in nodes}
        incoming: dict[str, int] = {node.id: 0 for node in nodes}
        for edge in edges:
            outgoing[edge.source].append(edge)
            incoming[edge.target] += 1

        start = triggers[0]
        if incoming[start.id] != 0 or len(outgoing[start.id]) != 1:
            raise ValueError("The trigger must be the graph root and have one outgoing edge.")

        for node in nodes:
            out = outgoing[node.id]
            if node.kind in {"condition.hour", "condition.weekday"}:
                if len(out) != 2 or {edge.when for edge in out} != {"true", "false"}:
                    raise ValueError(f"Condition '{node.id}' needs one true and one false branch.")
            elif len(out) > 1 or any(edge.when is not None for edge in out):
                raise ValueError(f"Node '{node.id}' can have only one unlabelled outgoing edge.")
        if any(incoming[node.id] > 1 for node in nodes):
            raise ValueError("A workflow node cannot have multiple incoming edges.")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Workflow graph contains a cycle.")
            if node_id in visited:
                return
            visiting.add(node_id)
            for edge in outgoing[node_id]:
                visit(edge.target)
            visiting.remove(node_id)
            visited.add(node_id)

        visit(start.id)
        if visited != set(by_id):
            raise ValueError("Every workflow node must be reachable from the trigger.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "nodes": [{"id": node.id, "type": node.kind, "config": node.config} for node in self.nodes],
            "edges": [
                {"from": edge.source, "to": edge.target, **({"when": edge.when} if edge.when else {})}
                for edge in self.edges
            ],
        }


@dataclass(frozen=True)
class WorkflowTrigger:
    kind: Literal["text", "hotkey", "schedule", "startup"]
    value: str
    workflow_id: str | None = None


@dataclass(frozen=True)
class WorkflowExecution:
    started: bool
    completed: bool
    steps: tuple[ToolResult, ...]
    message: str


class WorkflowGraphRunner:
    """Executes validated, acyclic graphs using only registered tools."""

    def __init__(
        self,
        registry: ToolRegistry,
        clock: Callable[[], datetime] = datetime.now,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.registry = registry
        self.clock = clock
        self.sleeper = sleeper

    @staticmethod
    def _normalize_phrase(value: str) -> str:
        return re.sub(r"\s+", " ", value.casefold()).strip()

    @staticmethod
    def _compare_hour(hour: int, operator: str, expected: int) -> bool:
        return {
            "eq": hour == expected,
            "lt": hour < expected,
            "lte": hour <= expected,
            "gt": hour > expected,
            "gte": hour >= expected,
        }[operator]

    def run(
        self,
        graph: WorkflowGraph,
        trigger: WorkflowTrigger,
        confirm: ConfirmCallback | None = None,
    ) -> WorkflowExecution:
        root = next(node for node in graph.nodes if node.kind.startswith("trigger."))
        expected_kind = root.kind.removeprefix("trigger.")
        if expected_kind == "text":
            expected_values = root.config.get("phrases", [root.config.get("phrase", "")])
        elif expected_kind == "hotkey":
            expected_value = root.config["hotkey"]
        elif expected_kind == "schedule":
            expected_value = root.config["time"]
        else:
            expected_value = ""

        if trigger.kind != expected_kind:
            return WorkflowExecution(False, False, (), "Trigger type does not match.")
        if expected_kind == "text":
            normalized_input = self._normalize_phrase(trigger.value)
            matches = normalized_input in {
                self._normalize_phrase(value) for value in expected_values
            }
        elif expected_kind == "startup":
            matches = trigger.value == ""
        else:
            matches = trigger.value.casefold() == expected_value.casefold()
        if not matches:
            return WorkflowExecution(False, False, (), "Trigger did not match.")

        by_id = {node.id: node for node in graph.nodes}
        outgoing: dict[str, list[GraphEdge]] = {node.id: [] for node in graph.nodes}
        for edge in graph.edges:
            outgoing[edge.source].append(edge)

        current = outgoing[root.id][0].target
        results: list[ToolResult] = []
        visits = 0
        while current:
            visits += 1
            if visits > 64:
                return WorkflowExecution(True, False, tuple(results), "Workflow step limit reached.")
            node = by_id[current]
            edges = outgoing[current]
            if node.kind == "condition.hour":
                cfg = node.config
                passed = self._compare_hour(self.clock().hour, cfg["operator"], cfg["value"])
                branch = "true" if passed else "false"
                current = next(edge.target for edge in edges if edge.when == branch)
                continue
            if node.kind == "condition.weekday":
                passed = self.clock().isoweekday() == node.config["value"]
                branch = "true" if passed else "false"
                current = next(edge.target for edge in edges if edge.when == branch)
                continue
            if node.kind == "action.repeat":
                for iteration in range(node.config["count"]):
                    result = self.registry.execute(
                        node.config["name"], node.config["arguments"], confirm
                    )
                    results.append(result)
                    if not result.ok:
                        return WorkflowExecution(
                            True, False, tuple(results),
                            f"Повтор {iteration + 1}/{node.config['count']}: {result.output}",
                        )
                current = edges[0].target if edges else ""
                continue
            if node.kind == "action.wait":
                seconds = float(node.config["seconds"])
                if seconds:
                    self.sleeper(seconds)
                result = ToolResult(True, f"Ожидание {seconds:g} сек.")
            elif node.kind == "action.tool":
                result = self.registry.execute(node.config["name"], node.config.get("arguments", {}), confirm)
            else:
                return WorkflowExecution(True, False, tuple(results), f"Unexpected node: {node.kind}")
            results.append(result)
            if not result.ok:
                return WorkflowExecution(True, False, tuple(results), result.output)
            current = edges[0].target if edges else ""

        return WorkflowExecution(True, True, tuple(results), "Сценарий выполнен.")
