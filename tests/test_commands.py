from hellsaiz_pc_ai.core.commands import CommandRouter
from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def make_router():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "get_local_time", "time",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE, lambda _: ToolResult(True, "13.11.2026 12:00"),
    ))
    registry.register(ToolSpec(
        "get_system_info", "system",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE, lambda _: ToolResult(True, "Windows 11"),
    ))
    registry.register(ToolSpec(
        "open_app", "open",
        {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]},
        RiskLevel.CONFIRM, lambda args: ToolResult(True, f"opened {args['app']}"),
    ))
    registry.register(ToolSpec(
        "set_volume", "volume",
        {"type": "object", "properties": {"percent": {"type": "integer"}}, "required": ["percent"]},
        RiskLevel.CONFIRM, lambda args: ToolResult(True, f"volume {args['percent']}"),
    ))
    registry.register(ToolSpec(
        "close_process", "close",
        {"type": "object", "properties": {"process": {"type": "string"}}, "required": ["process"]},
        RiskLevel.CONFIRM, lambda args: ToolResult(True, f"closed {args['process']}"),
    ))
    clipboard_content = {"value": ""}
    registry.register(ToolSpec(
        "read_clipboard", "read clipboard",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE, lambda _: ToolResult(True, "clipboard text"),
    ))
    registry.register(ToolSpec(
        "create_reminder", "create reminder",
        {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "minimum": 10, "maximum": 2592000},
                "message": {"type": "string", "minLength": 1, "maxLength": 300},
            },
            "required": ["seconds", "message"],
            "additionalProperties": False,
        },
        RiskLevel.CONFIRM, lambda args: ToolResult(
            True, f"reminder {args['seconds']}: {args['message']}"
        ),
    ))
    registry.register(ToolSpec(
        "list_reminders", "list reminders",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE, lambda _: ToolResult(True, "no reminders"),
    ))
    registry.register(ToolSpec(
        "dismiss_reminder", "dismiss reminder",
        {
            "type": "object",
            "properties": {"reminder_id": {"type": "integer", "minimum": 1}},
            "required": ["reminder_id"],
            "additionalProperties": False,
        },
        RiskLevel.CONFIRM, lambda args: ToolResult(True, f"dismissed {args['reminder_id']}"),
    ))
    registry.register(ToolSpec(
        "write_clipboard", "write clipboard",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 20000}},
            "required": ["text"],
            "additionalProperties": False,
        },
        RiskLevel.CONFIRM,
        lambda args: (
            clipboard_content.update(value=args["text"])
            or ToolResult(True, "clipboard updated")
        ),
    ))
    return CommandRouter(
        registry,
        {"notepad": ("notepad.exe",), "calculator": ("calc.exe",)},
        {"discord": "Discord.exe"},
    )


def approve(*_):
    return True


def deny(*_):
    return False


def test_help_is_local_and_does_not_need_model():
    assert "без ИИ" in make_router().route("помощь")


def test_time_command_routes_to_registered_tool():
    assert make_router().route("Хеллсайз, который час?") == "Готово. 13.11.2026 12:00"


def test_open_app_requires_confirmation():
    router = make_router()
    assert "отменено" in router.route("открой блокнот", deny).casefold()
    assert router.route("открой блокнот", approve) == "Готово. opened notepad"


def test_unlisted_app_does_not_execute():
    assert "не добавлено" in make_router().route("открой powershell").casefold()


def test_unknown_text_is_not_guessed():
    assert make_router().route("поговори со мной") is None


def test_volume_command_is_deterministic_and_range_checked():
    router = make_router()
    assert router.route("установи громкость на 30 процентов", approve) == "Готово. volume 30"
    assert "от 0 до 100" in router.route("установи громкость на 150").casefold()


def test_close_process_uses_allowlist_and_confirmation():
    router = make_router()
    assert "closed discord" in router.route("закрой дискорд", approve).casefold()
    assert "не добавлен" in router.route("закрой powershell").casefold()



def test_read_clipboard_requires_an_explicit_command():
    router = make_router()

    assert router.route("прочитай буфер обмена") == "Готово. clipboard text"
    assert router.route("что скопировано") == "Готово. clipboard text"
    assert router.route("поговори со мной") is None


def test_write_clipboard_preserves_text_and_requires_confirmation():
    router = make_router()

    denied = router.route("скопируй: Hello, World!", deny)
    assert "отменено" in denied.casefold()

    approved = router.route("Хеллсайз, скопируй Привет, Мир!", approve)
    assert approved == "Готово. clipboard updated"


def test_write_clipboard_accepts_multiline_payload():
    router = make_router()
    result = router.route("скопируй Первая строка\nВторая строка", approve)

    assert result == "Готово. clipboard updated"


def test_reminder_command_parses_seconds_minutes_and_hours():
    router = make_router()
    assert router.route("напомни через 30 секунд проверить") == (
        "Не выполнено. Действие отменено: подтверждение не получено."
    )
    assert router.route("Хеллсайз, напомни мне через 5 минут Проверить чайник", approve) == (
        "Готово. reminder 300: Проверить чайник"
    )
    assert router.route("напомни через 2 часа сделать перерыв", approve) == (
        "Готово. reminder 7200: сделать перерыв"
    )


def test_reminder_command_validates_delay_and_requires_confirmation():
    router = make_router()
    assert "отменено" in router.route("напомни через 5 минут позвонить", deny).casefold()
    assert "от 10 секунд" in router.route("напомни через 3 секунды позвонить").casefold()
    assert "формат" in router.route("напомни завтра позвонить").casefold()


def test_list_and_dismiss_reminders_are_explicit():
    router = make_router()
    assert router.route("мои напоминания") == "Готово. no reminders"
    assert router.route("удали напоминание 12", deny).startswith("Не выполнено.")
    assert router.route("удали напоминание 12", approve) == "Готово. dismissed 12"
