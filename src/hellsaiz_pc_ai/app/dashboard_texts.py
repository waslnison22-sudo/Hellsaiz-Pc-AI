from __future__ import annotations

from typing import Any


def greeting_for_hour(hour: int) -> str:
    """Map a clock hour to a natural Russian greeting."""
    if 5 <= hour < 12:
        return "Доброе утро"
    if 12 <= hour < 18:
        return "Добрый день"
    if 18 <= hour < 23:
        return "Добрый вечер"
    return "Доброй ночи"


def greeting_note(hour: int, persona: str) -> str:
    """A short human comment under the greeting, matching the assistant persona."""
    if str(persona or "").casefold() == "джарвис":
        if 5 <= hour < 12:
            return "Доброе утро, сэр. Системы на связи."
        if 12 <= hour < 18:
            return "День в разгаре. Я к вашим услугам, сэр."
        if 18 <= hour < 23:
            return "Чем могу помочь, сэр?"
        return "Ночная смена, сэр. Слушаю."
    if 5 <= hour < 12:
        return "Работаем в спокойном темпе."
    if 12 <= hour < 18:
        return "День идёт — я рядом."
    if 18 <= hour < 23:
        return "Сделаем тише и проще — день закончился."
    return "Ночная смена. Я на связи."


def reminders_count_label(count: int) -> str:
    """«1 напоминание на сегодня», «2 напоминания…», «5 напоминаний…»."""
    if count <= 0:
        return "На сегодня ничего нет"
    mod10, mod100 = count % 10, count % 100
    if mod10 == 1 and mod100 != 11:
        word = "напоминание"
    elif 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        word = "напоминания"
    else:
        word = "напоминаний"
    return f"{count} {word} на сегодня"


def system_comment(cpu_percent: float | None) -> str:
    """One living phrase under the CPU/RAM/GPU bars."""
    if cpu_percent is None:
        return "Метрики пока не считаны."
    if cpu_percent >= 80:
        return "Процессор сейчас трудится вовсю."
    if cpu_percent >= 40:
        return "Средняя нагрузка — всё под контролем."
    return "Работаем в спокойном темпе."


def last_reply_empty_note() -> str:
    """Shown on the last-reply card before the first assistant answer."""
    return "Пока тишина. Спроси меня о чём угодно."


def reminder_preview_line(reminder: Any) -> str:
    """One compact line for the reminders card."""
    due_label = reminder.due_at.astimezone().strftime("%d.%m %H:%M")
    return f"{due_label}  ·  {reminder.message}"


def preview_reminders(entries: list[Any], limit: int = 6) -> list[str]:
    """Compact reminder lines for the dashboard card."""
    return [reminder_preview_line(entry) for entry in entries[:max(1, limit)]]
