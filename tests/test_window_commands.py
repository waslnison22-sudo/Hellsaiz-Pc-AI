from hellsaiz_pc_ai.core.commands import CommandRouter
from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def make_router():
    registry = ToolRegistry()
    called = []

    for name in (
        "minimize_active_window",
        "maximize_active_window",
        "restore_active_window",
        "close_active_window",
    ):
        registry.register(ToolSpec(
            name,
            name,
            {"type": "object", "properties": {}, "additionalProperties": False},
            RiskLevel.CONFIRM,
            lambda _args, name=name: called.append(name) or ToolResult(True, name),
        ))
    router = CommandRouter(registry, {}, {}, {})
    return router, called


def test_active_window_phrases_map_to_registered_tools():
    router, called = make_router()
    expected = {
        "Хеллсайз, сверни окно": "minimize_active_window",
        "разверни текущее окно": "maximize_active_window",
        "верни окно": "restore_active_window",
        "закрой активное окно": "close_active_window",
    }

    for phrase, tool in expected.items():
        result = router.route(phrase)
        assert result == f"Готово. {tool}"

    assert called == list(expected.values())


def test_unknown_window_command_is_not_guessed():
    router, called = make_router()

    assert router.route("сверни все окна и выключи компьютер") is None
    assert called == []
