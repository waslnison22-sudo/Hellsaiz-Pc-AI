from __future__ import annotations

from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.tools.screen_ocr import (
    MAX_TEXT_CHARS,
    _extract_text,
    read_primary_screen_text,
    register_screen_ocr_tools,
)


class FakeResult:
    def __init__(self, texts, scores=None):
        self.txts = texts
        self.scores = scores


def test_ocr_extracts_text_and_filters_low_confidence():
    result = _extract_text(FakeResult(
        ["  Hellsaiz   PC AI ", "noise", "", "Version 0.1.4"],
        [0.99, 0.1, 0.8, 0.98],
    ))
    assert result == ["Hellsaiz PC AI", "Version 0.1.4"]


def test_ocr_limits_output_length():
    result = _extract_text(FakeResult(["x" * (MAX_TEXT_CHARS + 100)], [0.99]))
    assert len(result[0]) == MAX_TEXT_CHARS


def test_screen_capture_result_is_local_and_not_written():
    calls = []
    class FakeEngine:
        def __call__(self, image):
            calls.append(image)
            return FakeResult(["Local only"], [0.95])

    output = read_primary_screen_text(
        capture=lambda: "frame",
        engine_factory=FakeEngine,
    )
    assert output.ok
    assert "Local only" in output.output
    assert output.data == {
        "line_count": 1,
        "saved_to_disk": False,
        "sent_to_network": False,
    }
    assert calls == ["frame"]


def test_screen_ocr_reports_optional_dependency_failure():
    output = read_primary_screen_text(
        capture=lambda: "frame",
        engine_factory=lambda: (_ for _ in ()).throw(ImportError("missing")),
    )
    assert not output.ok
    assert "ImportError" in output.output


def test_ocr_tool_is_disabled_until_user_opt_in():
    registry = ToolRegistry()
    state = {"enabled": False}
    register_screen_ocr_tools(registry, enabled=lambda: state["enabled"])

    disabled = registry.execute("read_screen_text", {})
    assert not disabled.ok
    assert "выключено" in disabled.output.casefold()

    state["enabled"] = True
    # Once enabled, a mocked screen capture is tested by read_primary_screen_text.
    assert registry.get_spec("read_screen_text") is not None



def test_enabled_ocr_tool_uses_local_reader(monkeypatch):
    from hellsaiz_pc_ai.core.models import ToolResult
    from hellsaiz_pc_ai.tools import screen_ocr

    registry = ToolRegistry()
    register_screen_ocr_tools(registry, enabled=lambda: True)
    monkeypatch.setattr(
        screen_ocr,
        "read_primary_screen_text",
        lambda **_kwargs: ToolResult(True, "Visible text", {"sent_to_network": False}),
    )

    result = registry.execute("read_screen_text", {})

    assert result.ok
    assert result.output == "Visible text"
    assert result.data["sent_to_network"] is False


def test_enabled_ocr_tool_passes_user_model_directory_to_reader(monkeypatch, tmp_path):
    from hellsaiz_pc_ai.core.models import ToolResult
    from hellsaiz_pc_ai.tools import screen_ocr

    received = {}
    registry = ToolRegistry()
    register_screen_ocr_tools(
        registry,
        enabled=lambda: True,
        model_root=tmp_path,
    )

    def fake_reader(*, model_root=None):
        received["model_root"] = model_root
        return ToolResult(True, "Visible text")

    monkeypatch.setattr(screen_ocr, "read_primary_screen_text", fake_reader)
    result = registry.execute("read_screen_text", {})

    assert result.ok
    assert received["model_root"] == tmp_path
