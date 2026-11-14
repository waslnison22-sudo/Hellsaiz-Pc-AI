from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path

from hellsaiz_pc_ai.workflows.graph import WorkflowGraph


class WorkflowLibrary:
    """Stores validated JSON graphs and their local visual layout metadata."""

    _ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
    _NODE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
    _COORDINATE_LIMIT = 100_000.0

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.layout_directory = self.directory / ".layouts"

    @classmethod
    def _validate_id(cls, workflow_id: str) -> str:
        if not isinstance(workflow_id, str) or not cls._ID_PATTERN.fullmatch(workflow_id):
            raise ValueError("Workflow id must contain only letters, digits, '_' or '-'.")
        return workflow_id

    def save(self, workflow_id: str, graph: WorkflowGraph) -> Path:
        safe_id = self._validate_id(workflow_id)
        target = self.directory / f"{safe_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(graph.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(target)
        return target

    def load(self, workflow_id: str) -> WorkflowGraph:
        safe_id = self._validate_id(workflow_id)
        path = self.directory / f"{safe_id}.json"
        return WorkflowGraph.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def _normalize_layout(cls, data: object) -> dict[str, dict[str, float]]:
        if not isinstance(data, dict) or len(data) > 64:
            raise ValueError("Workflow layout must contain at most 64 nodes.")
        normalized: dict[str, dict[str, float]] = {}
        for node_id, position in data.items():
            if not isinstance(node_id, str) or not cls._NODE_PATTERN.fullmatch(node_id):
                raise ValueError("Invalid node id in workflow layout.")
            if not isinstance(position, dict) or set(position) != {"x", "y"}:
                raise ValueError(f"Layout position for '{node_id}' must contain x and y.")
            coordinates: dict[str, float] = {}
            for axis in ("x", "y"):
                value = position[axis]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"Layout coordinate {axis} for '{node_id}' must be numeric.")
                coordinate = float(value)
                if not math.isfinite(coordinate) or abs(coordinate) > cls._COORDINATE_LIMIT:
                    raise ValueError(f"Layout coordinate {axis} for '{node_id}' is out of range.")
                coordinates[axis] = round(coordinate, 2)
            normalized[node_id] = coordinates
        return normalized

    def save_layout(
        self, workflow_id: str, positions: dict[str, dict[str, float]]
    ) -> Path:
        safe_id = self._validate_id(workflow_id)
        normalized = self._normalize_layout(positions)
        self.layout_directory.mkdir(parents=True, exist_ok=True)
        target = self.layout_directory / f"{safe_id}.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return target

    def load_layout(self, workflow_id: str) -> dict[str, dict[str, float]]:
        safe_id = self._validate_id(workflow_id)
        path = self.layout_directory / f"{safe_id}.json"
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return self._normalize_layout(data)

    def list(self) -> list[tuple[str, WorkflowGraph]]:
        entries: list[tuple[str, WorkflowGraph]] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                graph = WorkflowGraph.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logging.warning("Skipping invalid workflow %s: %s", path.name, exc)
                continue
            entries.append((path.stem, graph))
        return entries

    def delete(self, workflow_id: str) -> None:
        safe_id = self._validate_id(workflow_id)
        path = self.directory / f"{safe_id}.json"
        if path.exists():
            path.unlink()
        layout_path = self.layout_directory / f"{safe_id}.json"
        if layout_path.exists():
            layout_path.unlink()
