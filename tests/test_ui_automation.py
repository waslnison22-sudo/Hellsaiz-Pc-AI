from __future__ import annotations

from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.tools import ui_automation


class FakeControl:
    def __init__(self, name, control_type="Button"):
        self.name = name
        self.element_info = type(
            "Info",
            (),
            {"name": name, "control_type": control_type, "automation_id": f"id-{name}"},
        )()
        self.clicked = 0
        self.focused = 0
        self.text = None
        self.name_reads = 0
        self.visibility_results = []
        self.enabled_results = []

    def window_text(self):
        self.name_reads += 1
        return self.name

    def is_visible(self):
        return self.visibility_results.pop(0) if self.visibility_results else True

    def is_enabled(self):
        return self.enabled_results.pop(0) if self.enabled_results else True

    def click_input(self):
        self.clicked += 1

    def set_focus(self):
        self.focused += 1

    def set_edit_text(self, value):
        self.text = value


class FakeWindow:
    def __init__(self, title, controls):
        self.title = title
        self.controls = controls

    def window_text(self):
        return self.title

    def descendants(self):
        return self.controls


class FakeDesktop:
    def __init__(self, windows):
        self._windows = windows

    def windows(self, visible_only=True):
        assert visible_only
        return self._windows


def test_inspect_window_lists_accessible_controls(monkeypatch):
    window = FakeWindow("Settings", [FakeControl("System"), FakeControl("Network")])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    result = ui_automation._inspect_window("Settings")

    assert result.ok
    assert "System" in result.output
    assert "Network" in result.output
    assert "[Button]" in result.output


def test_click_requires_one_exact_window_and_control(monkeypatch):
    save = FakeControl("Save")
    window = FakeWindow("Notepad", [save])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    result = ui_automation._click_control("Notepad", "Save")

    assert result.ok
    assert save.clicked == 1


def test_click_refuses_ambiguous_window_or_control(monkeypatch):
    first = FakeWindow("Chrome - mail", [FakeControl("Open")])
    second = FakeWindow("Chrome - docs", [FakeControl("Open")])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([first, second]))

    result = ui_automation._click_control("Chrome", "Open")

    assert not result.ok
    assert "несколько окон" in result.output.casefold()
    assert first.controls[0].clicked == 0
    assert second.controls[0].clicked == 0


def test_click_refuses_multiple_matching_controls(monkeypatch):
    first = FakeControl("Open")
    second = FakeControl("Open")
    window = FakeWindow("App", [first, second])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    result = ui_automation._click_control("App", "Open")

    assert not result.ok
    assert "неоднозначен" in result.output.casefold()
    assert first.clicked == 0
    assert second.clicked == 0


def test_type_text_only_enters_editable_control_and_is_literal(monkeypatch):
    field = FakeControl("Search", "Edit")
    window = FakeWindow("Explorer", [field])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    value = "find: quotes ' ; $(not a command) \n new line"
    result = ui_automation._type_into_control("Explorer", "Search", value)

    assert result.ok
    assert field.focused == 1
    assert field.text == value


def test_type_text_refuses_button_controls(monkeypatch):
    button = FakeControl("Search", "Button")
    window = FakeWindow("Explorer", [button])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    result = ui_automation._type_into_control("Explorer", "Search", "text")

    assert not result.ok
    assert button.text is None


def test_ui_automation_tool_schemas_validate_arguments():
    registry = ToolRegistry()
    ui_automation.register_ui_automation_tools(registry)

    assert registry.execute("click_window_control", {"window_title": "", "control_name": "Save"}).ok is False
    assert registry.execute(
        "type_into_window_control",
        {"window_title": "App", "control_name": "Search", "text": "x" * 4001},
    ).ok is False


def test_keyboard_shortcut_targets_one_window_and_uses_whitelist(monkeypatch):
    class FakeWindow:
        def __init__(self):
            self.focused = False
            self.sent = []

        def window_text(self):
            return "Browser"

        def set_focus(self):
            self.focused = True

        def type_keys(self, sequence, set_foreground=False):
            self.sent.append((sequence, set_foreground))

    window = FakeWindow()
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    result = ui_automation._send_keyboard_shortcut("Browser", "ctrl+l")

    assert result.ok
    assert window.focused
    assert window.sent == [("^l", True)]


def test_keyboard_shortcut_refuses_shell_and_arbitrary_key_combinations(monkeypatch):
    window = FakeWindow("Browser", [])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    result = ui_automation._send_keyboard_shortcut("Browser", "WIN+R")

    assert not result.ok
    assert "не разрешено" in result.output.casefold()


def test_control_selection_reuses_one_property_snapshot(monkeypatch):
    control = FakeControl("Save")
    window = FakeWindow("Settings", [control])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))
    result = ui_automation._click_control("Settings", "Save")

    assert result.ok
    assert control.name_reads == 1
    assert control.clicked == 1


def test_click_rechecks_visibility_before_using_a_stale_control(monkeypatch):
    control = FakeControl("Save")
    control.visibility_results = [True, False]
    window = FakeWindow("Settings", [control])
    monkeypatch.setattr(ui_automation, "_desktop", lambda: FakeDesktop([window]))

    result = ui_automation._click_control("Settings", "Save")

    assert not result.ok
    assert "недоступен" in result.output.casefold()
    assert control.clicked == 0

