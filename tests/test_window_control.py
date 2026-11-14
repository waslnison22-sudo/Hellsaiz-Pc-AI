import os

from hellsaiz_pc_ai.core.registry import ToolRegistry
from hellsaiz_pc_ai.tools import window_control


class FakeUser32:
    def __init__(self, title="Calculator"):
        self.title = title
        self.shown = []
        self.messages = []
        self.valid = True

    def GetForegroundWindow(self):
        return 101

    def IsWindow(self, hwnd):
        return self.valid

    def GetWindowTextLengthW(self, hwnd):
        return len(self.title)

    def GetWindowTextW(self, hwnd, buffer, size):
        buffer.value = self.title
        return len(self.title)

    def ShowWindowAsync(self, hwnd, command):
        self.shown.append((hwnd, command))
        return True

    def PostMessageW(self, hwnd, message, wparam, lparam):
        self.messages.append((hwnd, message, wparam, lparam))
        return True


def test_window_tools_are_registered_and_target_foreground_window(monkeypatch):
    fake = FakeUser32()
    monkeypatch.setattr(window_control, "_load_user32", lambda: fake)
    registry = ToolRegistry()
    window_control.register_window_tools(registry)

    result = registry.execute("minimize_active_window", {})

    assert result.ok
    assert "Calculator" in result.output
    assert fake.shown == [(101, window_control.SW_MINIMIZE)]


def test_maximize_and_restore_use_native_show_commands(monkeypatch):
    fake = FakeUser32("Notepad")
    monkeypatch.setattr(window_control, "_load_user32", lambda: fake)
    registry = ToolRegistry()
    window_control.register_window_tools(registry)

    assert registry.execute("maximize_active_window", {}).ok
    assert registry.execute("restore_active_window", {}).ok
    assert fake.shown == [
        (101, window_control.SW_MAXIMIZE),
        (101, window_control.SW_RESTORE),
    ]


def test_close_posts_normal_wm_close_message(monkeypatch):
    fake = FakeUser32("Calculator")
    monkeypatch.setattr(window_control, "_load_user32", lambda: fake)
    registry = ToolRegistry()
    window_control.register_window_tools(registry)

    result = registry.execute("close_active_window", {})

    assert result.ok
    assert fake.messages == [(101, window_control.WM_CLOSE, 0, 0)]


def test_window_controls_fail_when_no_foreground_window(monkeypatch):
    fake = FakeUser32()
    fake.valid = False
    monkeypatch.setattr(window_control, "_load_user32", lambda: fake)
    registry = ToolRegistry()
    window_control.register_window_tools(registry)

    result = registry.execute("minimize_active_window", {})

    assert not result.ok
    assert "активное окно" in result.output.casefold()
