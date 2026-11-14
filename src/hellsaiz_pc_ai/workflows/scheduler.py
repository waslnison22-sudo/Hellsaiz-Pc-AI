from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from hellsaiz_pc_ai.workflows.graph import WorkflowGraph, WorkflowTrigger
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary


class WorkflowScheduler:
    """Dispatches local startup and minute-based schedules while the app is running."""

    _STATE_LIMIT = 64 * 1024
    _FIRED_TOKEN = re.compile(r"^\d{4}-\d{2}-\d{2}@(?:[01]\d|2[0-3]):[0-5]\d$")

    def __init__(
        self,
        library: WorkflowLibrary,
        state_path: Path,
        clock=datetime.now,
    ) -> None:
        self.library = library
        self.state_path = state_path
        self.clock = clock
        self._startup_checked = False
        self._fired = self._load_state()

    def _load_state(self) -> dict[str, str]:
        if not self.state_path.is_file():
            return {}
        try:
            if self.state_path.stat().st_size > self._STATE_LIMIT:
                raise ValueError("Scheduler state file exceeds 64 KiB.")
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != {"fired"}:
                raise ValueError("Scheduler state has an invalid top-level schema.")
            fired = data["fired"]
            if not isinstance(fired, dict) or len(fired) > 512:
                raise ValueError("Scheduler state must contain at most 512 entries.")
            normalized: dict[str, str] = {}
            for workflow_id, token in fired.items():
                if (
                    not isinstance(workflow_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", workflow_id)
                    or not isinstance(token, str)
                    or not self._FIRED_TOKEN.fullmatch(token)
                ):
                    raise ValueError("Scheduler state contains an invalid entry.")
                normalized[workflow_id] = token
            return normalized
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logging.warning("Ignoring invalid workflow schedule state: %s", exc)
            return {}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"fired": self._fired}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    @staticmethod
    def _root(graph: WorkflowGraph):
        return next(node for node in graph.nodes if node.kind.startswith("trigger."))

    def poll(self, now: datetime | None = None) -> list[tuple[str, WorkflowTrigger]]:
        """Return events due in the current minute and startup events once per app session."""
        current = now or self.clock()
        due: list[tuple[str, WorkflowTrigger]] = []
        changed = False
        entries = self.library.list()

        if not self._startup_checked:
            self._startup_checked = True
            for workflow_id, graph in entries:
                root = self._root(graph)
                if root.kind == "trigger.startup":
                    due.append((workflow_id, WorkflowTrigger("startup", "")))

        token_time = current.strftime("%Y-%m-%d@%H:%M")
        for workflow_id, graph in entries:
            root = self._root(graph)
            if root.kind != "trigger.schedule":
                continue
            scheduled_time = root.config["time"]
            scheduled_days = root.config["days"]
            if current.isoweekday() not in scheduled_days:
                continue
            if current.strftime("%H:%M") != scheduled_time:
                continue
            if self._fired.get(workflow_id) == token_time:
                continue
            due.append((workflow_id, WorkflowTrigger("schedule", scheduled_time)))
            self._fired[workflow_id] = token_time
            changed = True

        if changed:
            self._save_state()
        return due
