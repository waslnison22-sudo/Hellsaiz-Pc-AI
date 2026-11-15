from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentMatch:
    """A recognized user intention and its extracted typed text slots."""

    name: str
    slots: dict[str, str]


@dataclass(frozen=True)
class IntentPattern:
    name: str
    pattern: re.Pattern[str]


class IntentEngine:
    """Small deterministic NLU layer: classify an utterance, then extract its slots."""

    def __init__(self) -> None:
        self._patterns: list[IntentPattern] = []

    def register(self, name: str, *patterns: str) -> None:
        if not name or not patterns:
            raise ValueError("An intent needs a name and at least one pattern.")
        compiled = [IntentPattern(name, re.compile(item, re.IGNORECASE)) for item in patterns]
        self._patterns.extend(compiled)

    def resolve(self, utterance: str) -> IntentMatch | None:
        normalized = unicodedata.normalize("NFKC", utterance).casefold().replace("ё", "е")
        normalized = " ".join(normalized.split()).strip(" \\t\\r\\n.,!?;:…")
        for item in self._patterns:
            match = item.pattern.fullmatch(normalized)
            if match is None:
                continue
            slots = {
                key: " ".join(value.split()).strip()
                for key, value in match.groupdict().items()
                if value is not None and value.strip()
            }
            if item.name == "exchange_rate":
                currency_forms = {
                    "доллара": "доллар",
                    "доллары": "доллар",
                    "доллару": "доллар",
                    "рубля": "рубль",
                    "рублю": "рубль",
                    "юаня": "юань",
                    "фунта": "фунт",
                }
                slots = {
                    key: currency_forms.get(value, value)
                    for key, value in slots.items()
                }
            return IntentMatch(item.name, slots)
        return None


def build_default_intent_engine() -> IntentEngine:
    engine = IntentEngine()
    engine.register(
        "web_search",
        r"(?:найди(?:\s+в\s+(?:интернете|сети))?|поищи(?:\s+в\s+(?:интернете|сети))?|загугли|поиск)\s+(?P<query>.+)",
        r"(?:найди информацию|поищи информацию|что известно|расскажи|проверь в интернете)\s+(?:о|об|про)?\s*(?P<query>.+)",
    )
    engine.register(
        "weather",
        r"(?:погода|какая погода|что с погодой)(?:\s+(?:сейчас|сегодня))?(?:\s+(?:в|для)\s+(?P<city>.+?))?(?:\s+(?:сейчас|сегодня))?",
    )
    engine.register(
        "exchange_rate",
        r"(?:курс(?: валют)?|сколько стоит)\s+"
        r"(?P<base>доллар(?:а|ы|у)?|usd|евро|eur|юан(?:ь|я)|cny|руб(?:ль|ля|лю)|rub|фунт(?:а)?|gbp)"
        r"(?:\s+(?:к|по отношению к)\s+"
        r"(?P<quote>доллар(?:а|ы|у)?|usd|евро|eur|юан(?:ь|я)|cny|руб(?:ль|ля|лю)|rub|фунт(?:а)?|gbp))?",
    )
    return engine
