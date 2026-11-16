from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def make_registry(risk=RiskLevel.CONFIRM):
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "perform_action", "test",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        risk, lambda _: ToolResult(True, "done")
    ))
    return registry


def test_confirm_risk_executes_without_callback():
    result = make_registry().execute("perform_action", {})
    assert result.ok
    assert result.output == "done"


def test_rejection_callback_cancels_action_before_handler():
    called = False
    handler_called = False

    def handler(_args):
        nonlocal handler_called
        handler_called = True
        return ToolResult(True, "done")

    registry = ToolRegistry()
    registry.register(ToolSpec(
        "perform_action", "test",
        {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        RiskLevel.CONFIRM, handler,
    ))

    def reject(spec, arguments):
        nonlocal called
        called = spec.name == "perform_action" and arguments == {}
        return False

    result = registry.execute("perform_action", {}, reject)
    assert not result.ok
    assert result.output == "Действие отменено пользователем."
    assert called is True
    assert handler_called is False


def test_accepted_confirmation_runs_registered_handler():
    called = []

    def approve(spec, arguments):
        called.append((spec.name, arguments))
        return True

    result = make_registry().execute("perform_action", {}, approve)
    assert result.ok
    assert called == [("perform_action", {})]


def test_confirmation_failure_fails_closed():
    registry = make_registry()
    result = registry.execute(
        "perform_action", {}, lambda *_: (_ for _ in ()).throw(RuntimeError("dialog failed"))
    )
    assert not result.ok
    assert "Не удалось получить подтверждение" in result.output


def test_unknown_arguments_are_rejected():
    assert not make_registry(RiskLevel.SAFE).execute("perform_action", {"unexpected": 1}).ok


def test_unknown_tool_is_rejected():
    assert not make_registry().execute("unregistered", {}).ok


def test_argument_type_and_numeric_limits_are_validated():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "set_volume", "volume",
        {
            "type": "object",
            "properties": {"percent": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["percent"],
            "additionalProperties": False,
        },
        RiskLevel.SAFE,
        lambda args: ToolResult(True, str(args["percent"])),
    ))
    assert registry.execute("set_volume", {"percent": 50}).ok
    assert not registry.execute("set_volume", {"percent": 101}).ok
    assert not registry.execute("set_volume", {"percent": True}).ok
    assert not registry.execute("set_volume", {"percent": "50"}).ok


def test_string_length_and_enum_are_validated():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "open", "open",
        {
            "type": "object",
            "properties": {"app": {"type": "string", "minLength": 1, "enum": ["notepad", "explorer"]}},
            "required": ["app"],
            "additionalProperties": False,
        },
        RiskLevel.SAFE,
        lambda args: ToolResult(True, args["app"]),
    ))
    assert not registry.execute("open", {"app": ""}).ok
    assert not registry.execute("open", {"app": "powershell"}).ok


def test_non_finite_numbers_are_rejected_before_tool_execution():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "set_level", "set level",
        {
            "type": "object",
            "properties": {"level": {"type": "number", "minimum": 0, "maximum": 1}},
            "required": ["level"],
            "additionalProperties": False,
        },
        RiskLevel.SAFE,
        lambda args: ToolResult(True, str(args["level"])),
    ))

    assert not registry.execute("set_level", {"level": float("nan")}).ok
    assert not registry.execute("set_level", {"level": float("inf")}).ok
    assert registry.execute("set_level", {"level": 0.5}).ok


def test_excessively_nested_tool_arguments_are_rejected():
    registry = ToolRegistry()
    schema = {"type": "string"}
    value = "payload"
    for _ in range(20):
        schema = {
            "type": "object",
            "properties": {"nested": schema},
            "required": ["nested"],
            "additionalProperties": False,
        }
        value = {"nested": value}
    registry.register(ToolSpec(
        "inspect_payload", "inspect",
        {
            "type": "object",
            "properties": {"payload": schema},
            "required": ["payload"],
            "additionalProperties": False,
        },
        RiskLevel.SAFE,
        lambda _args: ToolResult(True, "unexpected"),
    ))

    result = registry.execute("inspect_payload", {"payload": value})

    assert not result.ok
    assert "nesting depth" in result.output


def test_oversized_tool_collections_are_rejected():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "inspect_items", "inspect",
        {
            "type": "object",
            "properties": {"items": {"type": "array", "items": {"type": "integer"}}},
            "required": ["items"],
            "additionalProperties": False,
        },
        RiskLevel.SAFE,
        lambda _args: ToolResult(True, "unexpected"),
    ))

    result = registry.execute("inspect_items", {"items": list(range(1025))})

    assert not result.ok
    assert "collection size" in result.output


def test_validate_arguments_does_not_invoke_tool_handler():
    called = False

    def handler(_args):
        nonlocal called
        called = True
        return ToolResult(True, "done")

    registry = ToolRegistry()
    registry.register(ToolSpec(
        "perform_action", "test",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE, handler,
    ))

    validation = registry.validate_arguments("perform_action", {})

    assert validation.ok
    assert called is False

