from __future__ import annotations

import re
from typing import Any

from hellsaiz_pc_ai.core.models import ToolResult
from hellsaiz_pc_ai.core.registry import ConfirmCallback, ToolRegistry


HELP_TEXT = (
    "Доступные команды без ИИ:\n"
    "• «открой блокнот», «запусти калькулятор», «открой проводник»\n"
    "• «закрой дискорд» (только разрешённые процессы)\n"
    "• «установи громкость на 30 процентов»\n"
    "• «прочитай буфер обмена», «скопируй текст»\n"
    "• «напомни через 5 минут…», «мои напоминания»\n"
    "• «открой сайт example.com»\n"
    "• «который час», «какая дата», «информация о системе»\n"
    "• «заблокируй компьютер»\n"
    "• «помощь» или «список команд»\n\n"
    "Команды выполняются локально по заранее заданным правилам. "
    "Произвольный код и команды оболочки не запускаются."
)


class CommandRouter:
    """Deterministic command dispatcher. It never calls a language model."""

    APP_SYNONYMS = {
        "блокнот": "notepad",
        "notepad": "notepad",
        "калькулятор": "calculator",
        "calculator": "calculator",
        "проводник": "explorer",
        "файловый менеджер": "explorer",
        "explorer": "explorer",
        "steam": "steam",
        "стим": "steam",
        "cs2": "cs2",
        "кс2": "cs2",
        "кс 2": "cs2",
        "контр страйк 2": "cs2",
    }
    PROCESS_SYNONYMS = {
        "дискорд": "discord",
        "discord": "discord",
        "spotify": "spotify",
        "спотифай": "spotify",
    }
    OPEN_PREFIXES = (
        "открой мне ", "открыть мне ", "запусти мне ", "запустить мне ",
        "открой ", "открыть ", "запусти ", "запустить ", "запускай ",
        "включи ", "включить ", "вруби ", "стартуй ", "старт ", "подними ",
        "загрузи ", "open ", "launch ", "start ", "run ",
    )

    def __init__(
        self,
        registry: ToolRegistry,
        allowed_apps: dict[str, tuple[str, ...]],
        allowed_processes: dict[str, str] | None = None,
        app_aliases: dict[str, tuple[str, ...]] | None = None,
        wake_aliases: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        self.registry = registry
        self.allowed_apps = {name.casefold(): command for name, command in allowed_apps.items()}
        aliases = wake_aliases or ("Хеллсайз", "Хелсайз", "Хелл", "Hellsaiz", "Hell")
        self.wake_aliases = tuple(
            sorted({self._normalize_phrase(alias) for alias in aliases if alias.strip()}, key=len, reverse=True)
        )
        self.app_alias_lookup: dict[str, str] = {
            self._normalize_phrase(canonical): canonical
            for canonical in self.allowed_apps
        }
        for canonical, phrases in (app_aliases or {}).items():
            canonical_key = canonical.casefold()
            if canonical_key not in self.allowed_apps:
                raise ValueError(
                    f"Application aliases refer to an app outside the allowlist: {canonical_key}"
                )
            for phrase in (canonical_key, *phrases):
                normalized = self._normalize_phrase(phrase)
                owner = self.app_alias_lookup.get(normalized)
                if owner is not None and owner != canonical_key:
                    raise ValueError(f"Ambiguous application alias: {phrase}")
                self.app_alias_lookup[normalized] = canonical_key
        self.allowed_processes = {
            name.casefold(): executable for name, executable in (allowed_processes or {}).items()
        }

    @staticmethod
    def _normalize_phrase(text: str) -> str:
        return re.sub(r"\s+", " ", text.casefold()).strip()

    def strip_wake_name(self, text: str) -> str:
        value = text.strip()
        for wake_name in self.wake_aliases:
            match = re.match(
                rf"^{re.escape(wake_name)}(?=$|[\s,.:;!?-])",
                value,
                flags=re.IGNORECASE,
            )
            if match:
                return value[match.end():].lstrip(" \t,.:;!?-")
        return value

    def normalize(self, text: str) -> str:
        value = self.strip_wake_name(text)
        return re.sub(r"[\s.,!?;:]+", " ", value.casefold()).strip()

    def route(self, text: str, confirm: ConfirmCallback | None = None) -> str | None:
        command = self.normalize(text)
        if not command:
            return "Скажите или напишите команду. Для списка возможностей введите «помощь»."

        if command in {"помощь", "команды", "список команд", "что умеешь", "help", "/help"}:
            return HELP_TEXT

        if command in {"мои напоминания", "напоминания", "покажи напоминания", "список напоминаний"}:
            return self._execute("list_reminders", {}, confirm)

        dismiss_match = re.fullmatch(r"(?:удали|отмени) напоминание (\d+)", command)
        if dismiss_match:
            return self._execute(
                "dismiss_reminder", {"reminder_id": int(dismiss_match.group(1))}, confirm
            )

        reminder_match = re.match(
            r"^напомни(?: мне)?\s+через\s+(\d{1,5})\s+"
            r"(секунд(?:у|ы|а)?|сек|минут(?:у|ы|а)?|мин|час(?:а|ов)?|ч)\s+(.+?)\s*$",
            self.strip_wake_name(text),
            flags=re.IGNORECASE | re.DOTALL,
        )
        if reminder_match:
            amount = int(reminder_match.group(1))
            unit = reminder_match.group(2).casefold()
            factor = 1 if unit.startswith("сек") else 60 if unit.startswith("мин") else 3600
            seconds = amount * factor
            if not 10 <= seconds <= 2_592_000:
                return "Время напоминания должно быть от 10 секунд до 30 дней."
            message = reminder_match.group(3).strip()
            if not message:
                return "Добавь текст напоминания после времени."
            return self._execute(
                "create_reminder", {"seconds": seconds, "message": message}, confirm
            )
        if command.startswith("напомни"):
            return "Формат: «напомни через 5 минут проверить чайник». Допустимо от 10 секунд до 30 дней."

        if command in {
            "прочитай буфер обмена",
            "прочитай буфер",
            "что в буфере обмена",
            "что скопировано",
            "покажи буфер обмена",
        }:
            return self._execute("read_clipboard", {}, confirm)

        copy_match = re.match(
            r"^\s*скопируй(?:\s*[:,\-]\s*|\s+)([\s\S]+?)\s*$",
            self.strip_wake_name(text),
            flags=re.IGNORECASE,
        )
        if copy_match:
            clipboard_text = copy_match.group(1)
            if not clipboard_text:
                return "Укажи текст после команды «скопируй»."
            return self._execute("write_clipboard", {"text": clipboard_text}, confirm)
        if command == "скопируй":
            return "Укажи текст после команды «скопируй»."

        if command in {
            "который час", "сколько времени", "текущее время", "время", "какая дата",
            "какое сегодня число", "дата", "дата и время", "время и дата",
        }:
            return self._execute("get_local_time", {}, confirm)

        if command in {"информация о системе", "сведения о системе", "характеристики пк", "система"}:
            return self._execute("get_system_info", {}, confirm)

        if command in {"заблокируй компьютер", "заблокировать компьютер", "заблокируй пк"}:
            return self._execute("lock_pc", {}, confirm)

        volume_match = re.search(
            r"(?:установи|сделай|поставь)?\s*(?:системную\s+)?громкость(?:\s+на|\s+до)?\s+(\d{1,3})\s*(?:%|процентов?)?$",
            command,
        )
        if volume_match:
            percent = int(volume_match.group(1))
            if not 0 <= percent <= 100:
                return "Громкость должна быть от 0 до 100 процентов."
            return self._execute("set_volume", {"percent": percent}, confirm)

        for prefix in ("закрой ", "заверши "):
            if command.startswith(prefix):
                target = command[len(prefix):].strip()
                alias = self.PROCESS_SYNONYMS.get(target, target)
                if alias not in self.allowed_processes:
                    options = ", ".join(sorted(self.allowed_processes)) or "список пуст"
                    return f"Процесс «{target}» не добавлен в allowlist. Доступно: {options}."
                return self._execute("close_process", {"process": alias}, confirm)

        for prefix in self.OPEN_PREFIXES:
            if command.startswith(prefix):
                target = command[len(prefix):].strip()
                if not target:
                    return "Укажите, что нужно открыть."
                if target.startswith("сайт "):
                    return self._execute("open_url", {"url": target[5:].strip()}, confirm)
                if target.startswith("ссылку "):
                    return self._execute("open_url", {"url": target[7:].strip()}, confirm)
                if target in {"youtube", "ютуб"}:
                    return self._execute("open_url", {"url": "https://www.youtube.com"}, confirm)
                normalized_target = self._normalize_phrase(target)
                alias = self.app_alias_lookup.get(
                    normalized_target,
                    self.APP_SYNONYMS.get(normalized_target, normalized_target),
                )
                if alias not in self.allowed_apps:
                    options = ", ".join(sorted(self.allowed_apps)) or "нет разрешённых приложений"
                    return f"Приложение «{target}» не добавлено в список разрешённых. Доступно: {options}."
                return self._execute("open_app", {"app": alias}, confirm)

        return None

    def _execute(
        self, name: str, arguments: dict[str, Any], confirm: ConfirmCallback | None
    ) -> str:
        result: ToolResult = self.registry.execute(name, arguments, confirm)
        prefix = "Готово. " if result.ok else "Не выполнено. "
        return prefix + result.output
