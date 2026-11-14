from __future__ import annotations

from datetime import datetime

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.storage.reminders import (
    MAX_DELAY_SECONDS,
    MAX_MESSAGE_LENGTH,
    MIN_DELAY_SECONDS,
    ReminderStore,
)


def register_reminder_tools(registry: ToolRegistry, store: ReminderStore) -> None:
    def create(arguments: dict[str, object]) -> ToolResult:
        try:
            reminder = store.add(
                str(arguments["message"]),
                int(arguments["seconds"]),
            )
        except (TypeError, ValueError, OSError) as exc:
            return ToolResult(False, str(exc))
        due_label = reminder.due_at.astimezone().strftime("%d.%m.%Y %H:%M:%S")
        return ToolResult(
            True,
            f"Напоминание #{reminder.id} сохранено на {due_label}.",
            {"reminder_id": reminder.id, "due_at": reminder.due_at.isoformat()},
        )

    def list_all(_: dict[str, object]) -> ToolResult:
        reminders = store.list_pending()
        if not reminders:
            return ToolResult(True, "Активных напоминаний нет.", {"count": 0})
        lines = []
        for reminder in reminders:
            due_label = reminder.due_at.astimezone().strftime("%d.%m.%Y %H:%M")
            lines.append(f"#{reminder.id} — {due_label} — {reminder.message}")
        return ToolResult(True, "\n".join(lines), {"count": len(reminders)})

    def dismiss(arguments: dict[str, object]) -> ToolResult:
        try:
            reminder_id = int(arguments["reminder_id"])
            dismissed = store.dismiss(reminder_id)
        except (TypeError, ValueError, OSError) as exc:
            return ToolResult(False, str(exc))
        if not dismissed:
            return ToolResult(False, f"Активное напоминание #{reminder_id} не найдено.")
        return ToolResult(True, f"Напоминание #{reminder_id} отменено.")

    registry.register(
        ToolSpec(
            name="create_reminder",
            description="Сохранить локальное одноразовое напоминание с задержкой в секундах.",
            parameters={
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "minimum": MIN_DELAY_SECONDS,
                        "maximum": MAX_DELAY_SECONDS,
                    },
                    "message": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": MAX_MESSAGE_LENGTH,
                    },
                },
                "required": ["seconds", "message"],
                "additionalProperties": False,
            },
            risk=RiskLevel.CONFIRM,
            handler=create,
        )
    )
    registry.register(
        ToolSpec(
            name="list_reminders",
            description="Показать все активные локальные напоминания.",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk=RiskLevel.SAFE,
            handler=list_all,
        )
    )
    registry.register(
        ToolSpec(
            name="dismiss_reminder",
            description="Отменить активное напоминание по его положительному ID.",
            parameters={
                "type": "object",
                "properties": {
                    "reminder_id": {"type": "integer", "minimum": 1}
                },
                "required": ["reminder_id"],
                "additionalProperties": False,
            },
            risk=RiskLevel.CONFIRM,
            handler=dismiss,
        )
    )
