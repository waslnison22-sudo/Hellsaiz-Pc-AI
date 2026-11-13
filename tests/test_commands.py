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
    assert "закрыт" in router.route("закрой дискорд", approve).casefold()
    assert "не добавлен" in router.route("закрой powershell").casefold()
