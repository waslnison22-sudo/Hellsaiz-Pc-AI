from __future__ import annotations

from typing import Final


REPLY_STYLE_INSTRUCTIONS: Final[dict[str, str]] = {
    "brief": "Отвечай кратко: сначала прямой ответ, затем только необходимые детали. Не повторяй вопрос.",
    "normal": "Отвечай понятно и структурированно, с достаточным контекстом. Не перегружай ответ деталями.",
    "detailed": "Отвечай подробно: объясняй важные причины и шаги, используй примеры, когда они действительно помогают.",
}


def build_system_prompt(base_prompt: str, reply_style: str = "normal") -> str:
    """Append a validated Russian response-style instruction to the base prompt."""
    style = reply_style if reply_style in REPLY_STYLE_INSTRUCTIONS else "normal"
    base = base_prompt.strip()
    instruction = REPLY_STYLE_INSTRUCTIONS[style]
    return f"{base}\n\nСтиль ответа: {instruction}" if base else instruction
