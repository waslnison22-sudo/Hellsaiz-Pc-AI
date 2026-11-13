from __future__ import annotations

import json
import re
from pathlib import Path

from hellsaiz_pc_ai.workflows.graph import WorkflowGraph


class WorkflowLibrary:
    """Stores validated JSON graphs only; it never imports or executes user code."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_id(workflow_id: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", workflow_id):
            raise ValueError("Workflow id must contain only letters, digits, '_' or '-'.")
        return workflow_id

    def save(self, workflow_id: str, graph: WorkflowGraph) -> Path:
        safe_id = self._validate_id(workflow_id)
        target = self.directory / f"{safe_id}.json"
        temporary = target.with_suffix(".json.tmp")
        payload = json.dumps(graph.to_dict(), ensure_ascii=False, indent=2)
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(target)
        return target

    def load(self, workflow_id: str) -> WorkflowGraph:
        safe_id = self._validate_id(workflow_id)
        path = self.directory / f"{safe_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorkflowGraph.from_dict(data)

    def list(self) -> list[tuple[str, WorkflowGraph]]:
        entries: list[tuple[str, WorkflowGraph]] = []
        for path in sorted(self.directory.glob("*.json")):
            graph = WorkflowGraph.from_dict(json.loads(path.read_text(encoding="utf-8")))
            entries.append((path.stem, graph))
        return entries

    def delete(self, workflow_id: str) -> None:
        safe_id = self._validate_id(workflow_id)
        path = self.directory / f"{safe_id}.json"
        if path.exists():
            path.unlink()
