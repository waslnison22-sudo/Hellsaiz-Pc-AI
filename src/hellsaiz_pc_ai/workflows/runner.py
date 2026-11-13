from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hellsaiz_pc_ai.core.models import ToolResult
from hellsaiz_pc_ai.core.registry import ConfirmCallback, ToolRegistry


@dataclass(frozen=True)
class WorkflowStep:
    tool: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Workflow:
    name: str
    steps: tuple[WorkflowStep, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workflow:
        if set(data) - {"name", "steps"}:
            raise ValueError("Unsupported workflow field")
        name, raw_steps = data.get("name"), data.get("steps")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Workflow name is required")
        if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 32:
            raise ValueError("Workflow must contain 1..32 steps")
        steps: list[WorkflowStep] = []
        for item in raw_steps:
            if not isinstance(item, dict) or set(item) - {"tool", "arguments"}:
                raise ValueError("Step must contain only tool and arguments")
            tool, args = item.get("tool"), item.get("arguments", {})
            if not isinstance(tool, str) or not tool or not isinstance(args, dict):
                raise ValueError("Invalid workflow step")
            steps.append(WorkflowStep(tool, args))
        return cls(name.strip(), tuple(steps))


class WorkflowRunner:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def run(self, workflow: Workflow, confirm: ConfirmCallback | None = None) -> list[ToolResult]:
        results: list[ToolResult] = []
        for step in workflow.steps:
            result = self.registry.execute(step.tool, step.arguments, confirm)
            results.append(result)
            if not result.ok:
                break
        return results
