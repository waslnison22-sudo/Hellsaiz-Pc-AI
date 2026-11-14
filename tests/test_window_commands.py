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
        "list_windows",
    ):
        registry.register(ToolSpec(
            name,
            name,
            {"type": "object", "properties": {}, "additionalProperties": False},
            RiskLevel.CONFIRM,
            lambda _args, name=name: called.append((name, {})) or ToolResult(True, name),
        ))
    registry.register(ToolSpec(
        "focus_window",
        "focus a named window",
        {
            "type": "object",
            "properties": {"target": {"type": "string", "minLength": 1, "maxLength": 160}},
            "required": ["target"],
            "additionalProperties": False,
        },
        RiskLevel.CONFIRM,
        lambda args: called.append(("focus_window", args)) or ToolResult(True, args["target"]),
    ))
    for name, properties, required in (
        ("inspect_window_controls", {"window_title": {"type": "string"}}, ["window_title"]),
        (
            "click_window_control",
            {"window_title": {"type": "string"}, "control_name": {"type": "string"}},
            ["window_title", "control_name"],
        ),
        (
            "type_into_window_control",
            {
                "window_title": {"type": "string"},
                "control_name": {"type": "string"},
                "text": {"type": "string"},
            },
            ["window_title", "control_name", "text"],
        ),
    ):
        registry.register(ToolSpec(
            name,
            name,
            {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
            RiskLevel.CONFIRM,
            lambda args, name=name: called.append((name, args)) or ToolResult(True, str(args)),
        ))
    registry.register(ToolSpec(
        "send_keyboard_shortcut",
        "send an allowed shortcut",
        {
            "type": "object",
            "properties": {
                "window_title": {"type": "string"},
                "shortcut": {"type": "string", "enum": ["CTRL+L", "F5"]},
            },
            "required": ["window_title", "shortcut"],
            "additionalProperties": False,
        },
        RiskLevel.CONFIRM,
        lambda args: called.append(("send_keyboard_shortcut", args)) or ToolResult(True, "shortcut"),
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

    assert [name for name, _ in called] == list(expected.values())


def test_window_inventory_and_focus_phrases_extract_target():
    router, called = make_router()

    assert router.route("покажи открытые окна") == "Готово. list_windows"
    assert router.route("переключись на Steam") == "Готово. steam"
    assert router.route("активируй окно браузер Google Chrome") == "Готово. браузер google chrome"

    assert called == [
        ("list_windows", {}),
        ("focus_window", {"target": "steam"}),
        ("focus_window", {"target": "браузер google chrome"}),
    ]


def test_unknown_window_command_is_not_guessed():
    router, called = make_router()

    assert router.route("сверни все окна и выключи компьютер") is None
    assert called == []



def test_ui_automation_phrases_route_to_scoped_tools():
    router, called = make_router()

    router.route("покажи элементы окна Настройки")
    router.route("нажми Сохранить в окне Блокнот")
    router.route('Хеллсайз, введи "hello, world!" в поле Поиск окна Проводник')

    assert called[-3:] == [
        ("inspect_window_controls", {"window_title": "настройки"}),
        ("click_window_control", {"control_name": "сохранить", "window_title": "блокнот"}),
        (
            "type_into_window_control",
            {"text": "hello, world!", "control_name": "Поиск", "window_title": "Проводник"},
        ),
    ]


def test_keyboard_shortcut_voice_command_uses_scoped_safe_schema():
    router, called = make_router()

    router.route("нажми сочетание Ctrl+L в окне Браузер")
    router.route("нажми F5 в окне Проводник")

    assert called[-2:] == [
        ("send_keyboard_shortcut", {"shortcut": "CTRL+L", "window_title": "Браузер"}),
        ("send_keyboard_shortcut", {"shortcut": "F5", "window_title": "Проводник"}),
    ]


def test_unlisted_keyboard_shortcut_is_rejected_by_schema():
    router, called = make_router()

    result = router.route("нажми сочетание Win+R в окне Рабочий стол")

    assert "ошибка" in result.casefold() or "отклонены" in result.casefold()
    assert called == []
