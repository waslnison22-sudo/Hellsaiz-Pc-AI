"""Short RU phrases the companion shows on assistant events (≤60 characters)."""

from __future__ import annotations

import random

PHRASES: dict[str, tuple[str, ...]] = {
    "reminder_done": (
        "Напоминание выполнили — красота.",
        "Ещё одно дело закрыто.",
        "Пункт вычеркнут, идём дальше.",
    ),
    "scenario_started": (
        "Сценарий запущен, всё по плану.",
        "Автоматика сработала.",
        "Сделал, как договаривались.",
    ),
    "error": (
        "Что-то пошло не так — попробуем ещё.",
        "Сбой. Я рядом, повторим.",
        "Не вышло с первого раза.",
    ),
    "level_up": (
        "Мы сработались, спасибо!",
        "С каждым днём ближе.",
        "Приятно быть полезным.",
    ),
    "pet": (
        "Мурр. Продолжаем.",
        "Спасибо, приятно.",
        "Я тут, рядом.",
    ),
}

MAX_PHRASE_LEN = 60


def phrase_for(event: str, *, seed: int | None = None) -> str:
    """Pick a short line for an event; unknown events return an empty string."""
    variants = PHRASES.get(event, ())
    if not variants:
        return ""
    chooser = random.Random(seed) if seed is not None else random
    line = chooser.choice(variants)
    return line[:MAX_PHRASE_LEN]
