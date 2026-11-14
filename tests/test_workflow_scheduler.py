from datetime import datetime
from pathlib import Path

from hellsaiz_pc_ai.workflows.graph import WorkflowGraph
from hellsaiz_pc_ai.workflows.library import WorkflowLibrary
from hellsaiz_pc_ai.workflows.scheduler import WorkflowScheduler


def graph(kind, config):
    return WorkflowGraph.from_dict({
        "name": kind,
        "nodes": [
            {"id": "start", "type": kind, "config": config},
            {"id": "end", "type": "action.wait", "config": {"seconds": 0}},
        ],
        "edges": [{"from": "start", "to": "end"}],
    })


def test_startup_workflow_is_dispatched_once_per_scheduler_session(tmp_path):
    library = WorkflowLibrary(tmp_path / "workflows")
    library.save("startup", graph("trigger.startup", {}))
    scheduler = WorkflowScheduler(library, tmp_path / "state.json")

    first = scheduler.poll(datetime(2026, 11, 14, 8, 0))
    second = scheduler.poll(datetime(2026, 11, 14, 8, 1))

    assert [(item_id, trigger.kind) for item_id, trigger in first] == [("startup", "startup")]
    assert second == []


def test_schedule_fires_once_and_persists_state(tmp_path):
    library = WorkflowLibrary(tmp_path / "workflows")
    library.save(
        "weekday",
        graph("trigger.schedule", {"time": "09:30", "days": [1, 2, 3, 4, 5]}),
    )
    state_path = tmp_path / "schedule.json"
    scheduler = WorkflowScheduler(library, state_path)
    monday = datetime(2026, 11, 16, 9, 30)

    due = scheduler.poll(monday)
    repeat = scheduler.poll(monday.replace(second=30))
    restarted = WorkflowScheduler(library, state_path)
    after_restart = restarted.poll(monday)

    assert [(item_id, trigger.value) for item_id, trigger in due] == [("weekday", "09:30")]
    assert repeat == []
    assert after_restart == []


def test_schedule_respects_iso_weekday(tmp_path):
    library = WorkflowLibrary(tmp_path / "workflows")
    library.save(
        "weekday",
        graph("trigger.schedule", {"time": "09:30", "days": [1, 2, 3, 4, 5]}),
    )
    scheduler = WorkflowScheduler(library, tmp_path / "schedule.json")

    saturday = scheduler.poll(datetime(2026, 11, 14, 9, 30))

    assert saturday == []


def test_schedule_only_fires_in_matching_minute(tmp_path):
    library = WorkflowLibrary(tmp_path / "workflows")
    library.save(
        "daily",
        graph("trigger.schedule", {"time": "09:30", "days": [1, 2, 3, 4, 5, 6, 7]}),
    )
    scheduler = WorkflowScheduler(library, tmp_path / "schedule.json")

    assert scheduler.poll(datetime(2026, 11, 16, 9, 29)) == []
    assert scheduler.poll(datetime(2026, 11, 16, 9, 30))
    assert scheduler.poll(datetime(2026, 11, 16, 9, 31)) == []
