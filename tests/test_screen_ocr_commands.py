from hellsaiz_pc_ai.core.commands import CommandRouter
from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec


def test_screen_ocr_phrases_route_to_explicit_local_tool():
    registry = ToolRegistry()
    calls = []
    registry.register(ToolSpec(
        "read_screen_text",
        "Read screen text locally",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.CONFIRM,
        lambda _args: calls.append("ocr") or ToolResult(True, "Recognized text"),
    ))
    router = CommandRouter(registry, {}, {}, {})

    assert router.route("прочитай текст на экране") == "Готово. Recognized text"
    assert router.route("что написано на экране") == "Готово. Recognized text"
    assert calls == ["ocr", "ocr"]
