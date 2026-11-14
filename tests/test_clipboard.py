from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.tools import clipboard


def test_clipboard_module_fails_closed_outside_windows(monkeypatch):
    monkeypatch.setattr(clipboard.os, "name", "posix")

    try:
        clipboard.read_clipboard_text()
    except OSError as exc:
        assert "Windows" in str(exc)
    else:
        raise AssertionError("Clipboard access unexpectedly succeeded outside Windows")


def test_registered_read_tool_reads_only_when_called(monkeypatch):
    values = {"count": 0}
    monkeypatch.setattr(
        clipboard,
        "read_clipboard_text",
        lambda: values.update(count=values["count"] + 1) or "Секретный текст",
    )
    registry = ToolRegistry()
    clipboard.register_clipboard_tools(registry)

    assert values["count"] == 0
    result = registry.execute("read_clipboard", {})

    assert result.ok
    assert result.output == "Секретный текст"
    assert values["count"] == 1


def test_write_tool_executes_explicit_write_without_confirmation(monkeypatch):
    captured = []
    monkeypatch.setattr(clipboard, "write_clipboard_text", captured.append)
    registry = ToolRegistry()
    clipboard.register_clipboard_tools(registry)
    text = "Привет, Мир!\nВторая строка"

    result = registry.execute(
        "write_clipboard", {"text": text}, confirm=lambda *_: False
    )
    assert result.ok
    assert captured == [text]


def test_clipboard_write_rejects_empty_or_oversized_text(monkeypatch):
    monkeypatch.setattr(clipboard, "write_clipboard_text", lambda _: None)
    registry = ToolRegistry()
    clipboard.register_clipboard_tools(registry)

    empty = registry.execute("write_clipboard", {"text": ""}, confirm=lambda *_: True)
    oversized = registry.execute(
        "write_clipboard",
        {"text": "x" * (clipboard.MAX_WRITE_CHARS + 1)},
        confirm=lambda *_: True,
    )

    assert not empty.ok
    assert not oversized.ok


def test_clipboard_read_and_write_tools_are_registered():
    registry = ToolRegistry()
    clipboard.register_clipboard_tools(registry)
    tools = {tool["function"]["name"]: tool for tool in registry.openai_schemas()}

    assert tools["read_clipboard"]["function"]["name"] == "read_clipboard"
    assert tools["write_clipboard"]["function"]["name"] == "write_clipboard"
