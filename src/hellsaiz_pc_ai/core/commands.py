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
    }
    PROCESS_SYNONYMS = {
        "дискорд": "discord",
        "discord": "discord",
        "spotify": "spotify",
        "спотифай": "spotify",
    }
    OPEN_PREFIXES = ("открой ", "открыть ", "запусти ", "запустить ", "open ", "launch ")

    def __init__(
        self,
        registry: ToolRegistry,
        allowed_apps: dict[str, tuple[str, ...]],
        allowed_processes: dict[str, str] | None = None,
    ) -> None:
        self.registry = registry
        self.allowed_apps = {name.casefold(): command for name, command in allowed_apps.items()}
        self.allowed_processes = {
            name.casefold(): executable for name, executable in (allowed_processes or {}).items()
        }

    @staticmethod
    def normalize(text: str) -> str:
        value = re.sub(r"[\s.,!?;:]+", " ", text.casefold()).strip()
        for wake_word in ("хеллсайз ", "hellsaiz ", "хелсайз "):
            if value.startswith(wake_word):
                value = value[len(wake_word):].strip()
        return value

    def route(self, text: str, confirm: ConfirmCallback | None = None) -> str | None:
        command = self.normalize(text)
        if not command:
            return "Скажите или напишите команду. Для списка возможностей введите «помощь»."

        if command in {"помощь", "команды", "список команд", "что умеешь", "help", "/help"}:
            return HELP_TEXT

        if command in {
            "прочитай буфер обмена",
            "прочитай буфер",
            "что в буфере обмена",
            "что скопировано",
            "покажи буфер обмена",
        }:
            return self._execute("read_clipboard", {}, confirm)

        copy_match = re.match(
            r"^\s*(?:(?:хеллсайз|hellsaiz|хелсайз)\b[\s,.:;!?-]*)?"
            r"скопируй(?:\s*[:,\-]\s*|\s+)([\s\S]+?)\s*$",
            text,
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
                alias = self.APP_SYNONYMS.get(target, target)
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
