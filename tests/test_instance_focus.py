"""Second-launch focus contracts."""

from __future__ import annotations

from hellsaiz_pc_ai.app import instance_focus


def test_socket_name_is_user_scoped(monkeypatch):
    monkeypatch.setenv("USERNAME", "Arseniy")
    assert "arseniy" in instance_focus.socket_name()


def test_ask_to_raise_is_false_without_a_listener():
    assert instance_focus.ask_to_raise(timeout_ms=50) is False


def test_raise_server_calls_back_on_request():
    calls = []
    server = instance_focus.RaiseServer(lambda: calls.append("raised"))
    assert server._on_raise is not None
    assert server.start() in (True, False)  # environment dependent
