from datetime import datetime

from hellsaiz_pc_ai.app.dashboard_texts import (
    greeting_for_hour,
    greeting_note,
    preview_reminders,
    reminder_preview_line,
)


def test_greeting_matches_time_of_day():
    assert greeting_for_hour(6) == "Доброе утро"
    assert greeting_for_hour(12) == "Добрый день"
    assert greeting_for_hour(19) == "Добрый вечер"
    assert greeting_for_hour(2) == "Доброй ночи"
    assert greeting_for_hour(23) == "Доброй ночи"


def test_greeting_note_respects_persona():
    assert "сэр" in greeting_note(14, "джарвис")
    note = greeting_note(14, "хеллсайз")
    assert "сэр" not in note.casefold()
    assert note


def test_reminder_preview_line_is_compact():
    class Reminder:
        id = 7

        def __init__(self) -> None:
            self.due_at = datetime(2026, 11, 20, 22, 0)
            self.message = "проверить чайник"

    expected = datetime(2026, 11, 20, 22, 0).astimezone().strftime("%d.%m %H:%M")
    line = reminder_preview_line(Reminder())
    assert expected in line
    assert "проверить чайник" in line


def test_preview_reminders_limits_output():
    class Reminder:
        def __init__(self, index: int) -> None:
            self.due_at = datetime(2026, 11, 20, 22, 0)
            self.message = f"дело {index}"

    lines = preview_reminders([Reminder(i) for i in range(9)], limit=6)
    assert len(lines) == 6
    assert all("дело" in line for line in lines)
