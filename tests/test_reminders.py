from datetime import UTC, datetime, timedelta

import pytest

from hellsaiz_pc_ai.storage.reminders import ReminderStore


def test_reminder_is_persisted_and_survives_store_recreation(tmp_path):
    database = tmp_path / "assistant.sqlite3"
    now = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
    reminder = ReminderStore(database).add("Проверить чайник", 300, now=now)

    restored = ReminderStore(database).list_pending()

    assert len(restored) == 1
    assert restored[0].id == reminder.id
    assert restored[0].message == "Проверить чайник"
    assert restored[0].due_at == now + timedelta(minutes=5)


def test_due_reminder_is_returned_only_once(tmp_path):
    store = ReminderStore(tmp_path / "assistant.sqlite3")
    now = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
    reminder = store.add("Пора сделать перерыв", 60, now=now)

    early = store.take_due(now=now + timedelta(seconds=59))
    due = store.take_due(now=now + timedelta(seconds=60))
    repeated = store.take_due(now=now + timedelta(minutes=5))

    assert early == []
    assert [item.id for item in due] == [reminder.id]
    assert repeated == []
    assert store.list_pending() == []


def test_dismissed_reminder_does_not_fire(tmp_path):
    store = ReminderStore(tmp_path / "assistant.sqlite3")
    now = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
    reminder = store.add("Отменить тест", 10, now=now)

    assert store.dismiss(reminder.id)
    assert not store.dismiss(reminder.id)
    assert store.take_due(now=now + timedelta(minutes=1)) == []


@pytest.mark.parametrize("seconds", [0, 9, 2_592_001, True, 1.5])
def test_reminder_delay_is_bounded(seconds, tmp_path):
    store = ReminderStore(tmp_path / "assistant.sqlite3")

    with pytest.raises(ValueError, match="Reminder delay"):
        store.add("Тест", seconds)


def test_reminder_rejects_naive_clock_and_empty_message(tmp_path):
    store = ReminderStore(tmp_path / "assistant.sqlite3")

    with pytest.raises(ValueError, match="timezone-aware"):
        store.add("Тест", 10, now=datetime(2026, 11, 14, 8, 0))

    with pytest.raises(ValueError, match="1..300"):
        store.add("   ", 10)
