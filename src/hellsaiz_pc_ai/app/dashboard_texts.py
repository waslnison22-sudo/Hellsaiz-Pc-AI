from __future__ import annotations

from typing import Any


QUICK_COMMANDS = (
    "помощь",
    "открой блокнот",
    "сколько сейчас времени",
    "напомни в 22:00 проверить чайник",
    "погода",
)


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
            return "Вечер в разгаре? Я к вашим услугам, сэр."
        if 18 <= hour < 23:
            return "Чем могу помочь, сэр?"
        return "Ночная смена, сэр. Слушаю."
    if 5 <= hour < 12:
        return "Проверь план дня — я на связи."
    if 12 <= hour < 18:
        return "Скажи — компьютер сделает."
    if 18 <= hour < 23:
        return "Вечер. Скажи, что нужно сделать."
    return "Не спится? Скажи, что сделать."


def reminder_preview_line(reminder: Any) -> str:
    """One compact line for the reminders card."""
    due_label = reminder.due_at.astimezone().strftime("%d.%m %H:%M")
    return f"{due_label}  ·  {reminder.message}"


def preview_reminders(entries: list[Any], limit: int = 6) -> list[str]:
    """Compact reminder lines for the dashboard card."""
    return [reminder_preview_line(entry) for entry in entries[:max(1, limit)]]
