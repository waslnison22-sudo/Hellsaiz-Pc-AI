from hellsaiz_pc_ai.core.commands import ACKNOWLEDGMENTS, CommandRouter
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

    for _phrase in ("прочитай текст на экране", "что написано на экране"):
        reply = router.route(_phrase)
        assert any(reply.startswith(ack) for ack in ACKNOWLEDGMENTS)
        assert reply.endswith("Recognized text")
    assert calls == ["ocr", "ocr"]
