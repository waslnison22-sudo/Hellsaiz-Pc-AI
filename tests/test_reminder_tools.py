from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.tools.reminders import register_reminder_tools
from hellsaiz_pc_ai.storage.reminders import ReminderStore


def test_reminder_tools_use_confirmation_for_persistent_changes(tmp_path):
    store = ReminderStore(tmp_path / "assistant.sqlite3")
    registry = ToolRegistry()
    register_reminder_tools(registry, store)

    denied = registry.execute(
        "create_reminder",
        {"seconds": 60, "message": "Test"},
        confirm=lambda *_: False,
    )
    assert not denied.ok
    assert store.list_pending() == []

    allowed = registry.execute(
        "create_reminder",
        {"seconds": 60, "message": "Test"},
        confirm=lambda *_: True,
    )
    assert allowed.ok
    assert len(store.list_pending()) == 1


def test_reminder_list_and_dismiss_tools(tmp_path):
    store = ReminderStore(tmp_path / "assistant.sqlite3")
    registry = ToolRegistry()
    register_reminder_tools(registry, store)
    reminder = store.add("Проверка", 600)

    listed = registry.execute("list_reminders", {})
    assert listed.ok and f"#{reminder.id}" in listed.output

    dismissed = registry.execute(
        "dismiss_reminder",
        {"reminder_id": reminder.id},
        confirm=lambda *_: True,
    )
    assert dismissed.ok
    assert store.list_pending() == []
