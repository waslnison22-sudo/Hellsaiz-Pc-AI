from __future__ import annotations

import pytest

from hellsaiz_pc_ai.core.models import RiskLevel, ToolResult
from hellsaiz_pc_ai.core.registry import ToolRegistry, ToolSpec
from hellsaiz_pc_ai.telegram.config import (
    TelegramSettings,
    load_settings,
    save_settings,
    validate_bot_token,
)
from hellsaiz_pc_ai.telegram.worker import TelegramBotWorker


TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


def make_registry():
    registry = ToolRegistry()
    registry.register(ToolSpec(
        "get_local_time",
        "Read local time",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE,
        lambda _args: ToolResult(True, "12:34"),
    ))
    registry.register(ToolSpec(
        "get_system_info",
        "Read system info",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE,
        lambda _args: ToolResult(True, "Windows 11"),
    ))
    registry.register(ToolSpec(
        "list_reminders",
        "List reminders",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.SAFE,
        lambda _args: ToolResult(True, "No reminders"),
    ))
    registry.register(ToolSpec(
        "unsafe_action",
        "Unsafe action",
        {"type": "object", "properties": {}, "additionalProperties": False},
        RiskLevel.CONFIRM,
        lambda _args: ToolResult(True, "executed"),
    ))
    return registry


def make_worker(**kwargs):
    defaults = {
        "token": TOKEN,
        "registry": make_registry(),
        "allowed_user_ids": {111},
        "allowed_chat_ids": {222},
        "allowed_tools": {"get_local_time"},
        "proxy_url": "http://127.0.0.1:10809",
        "require_proxy": True,
        "api_call": lambda _method, _payload: {"ok": True, "result": []},
    }
    defaults.update(kwargs)
    return TelegramBotWorker(**defaults)


def test_token_validation_never_accepts_short_or_malformed_tokens():
    assert validate_bot_token(TOKEN) == TOKEN
    with pytest.raises(ValueError):
        validate_bot_token("abc:token")
    with pytest.raises(ValueError):
        validate_bot_token("123456:bad/token")


def test_unauthorized_user_or_chat_is_ignored():
    worker = make_worker()
    assert worker._handle_message({
        "from": {"id": 999},
        "chat": {"id": 222},
        "text": "/time",
    }) is None
    assert worker._handle_message({
        "from": {"id": 111},
        "chat": {"id": 999},
        "text": "/time",
    }) is None


def test_safe_commands_require_explicit_per_tool_permission():
    worker = make_worker()
    assert worker._handle_message({
        "from": {"id": 111},
        "chat": {"id": 222},
        "text": "/time",
    }) == (222, "12:34")
    assert worker._handle_message({
        "from": {"id": 111},
        "chat": {"id": 222},
        "text": "/system",
    }) == (222, "Эта команда отключена в матрице разрешений Telegram.")
    assert worker._handle_message({
        "from": {"id": 111},
        "chat": {"id": 222},
        "text": "/help",
    })[0] == 222


def test_unsafe_tools_are_never_allowed_even_when_injected():
    worker = make_worker(allowed_tools={"unsafe_action"})
    assert worker._execute_safe_tool("unsafe_action") == "Инструмент не прошёл проверку политики безопасности."


def test_user_id_and_chat_id_must_both_match():
    worker = make_worker()
    assert worker._handle_message({
        "from": {"id": 111},
        "chat": {"id": 222},
        "text": "/status",
    }) == (222, "Hellsaiz PC AI unknown: Telegram worker работает. LLM не используется.")


def test_command_parser_ignores_non_text_and_non_commands():
    worker = make_worker()
    assert worker._handle_message({
        "from": {"id": 111},
        "chat": {"id": 222},
        "photo": [{"file_id": "x"}],
    }) == (222, "Неизвестная команда. Отправь /help.")


def test_telegram_settings_are_disabled_by_default_and_persist(tmp_path: Path):
    path = tmp_path / "telegram.json"
    loaded = load_settings(path)
    assert not loaded.enabled
    assert loaded.allowed_user_ids == []
    assert loaded.allowed_chat_ids == []
    settings = TelegramSettings(True, [111], [222], ["get_local_time", "list_reminders"])
    save_settings(path, settings)
    restored = load_settings(path)
    assert restored.enabled
    assert restored.allowed_user_ids == [111]
    assert restored.allowed_chat_ids == [222]
    assert restored.allowed_tools == ["get_local_time", "list_reminders"]


def test_telegram_settings_reject_unknown_and_write_tools(tmp_path: Path):
    path = tmp_path / "telegram.json"
    path.write_text(
        '{"schema_version":1,"enabled":true,"allowed_user_ids":[1],"allowed_chat_ids":[2],'
        '"allowed_tools":["create_reminder"]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_settings(path)



def test_telegram_token_is_persisted_outside_json_and_reloaded(monkeypatch, tmp_path: Path):
    from hellsaiz_pc_ai.telegram import config

    protected = {}

    def fake_save(path, value):
        protected[str(path)] = "dpapi:" + value

    def fake_load(path):
        return protected.get(str(path), "").removeprefix("dpapi:")

    def fake_delete(path):
        protected.pop(str(path), None)

    monkeypatch.setattr(config, "save_secret", fake_save)
    monkeypatch.setattr(config, "load_secret", fake_load)
    monkeypatch.setattr(config, "delete_secret", fake_delete)

    settings_path = tmp_path / "telegram.json"
    settings = TelegramSettings(
        enabled=True,
        allowed_user_ids=[111],
        allowed_chat_ids=[222],
        allowed_tools=["get_local_time"],
        token=TOKEN,
    )
    save_settings(settings_path, settings)
    raw = settings_path.read_text(encoding="utf-8")
    assert TOKEN not in raw
    assert "token" not in raw
    assert protected[str(settings_path.with_name("telegram_token.dpapi"))] == "dpapi:" + TOKEN
    assert load_settings(settings_path).token == TOKEN


def test_dpapi_failure_does_not_write_enabled_telegram_config(monkeypatch, tmp_path: Path):
    from hellsaiz_pc_ai.telegram import config

    settings_path = tmp_path / "telegram.json"

    def fail_save(_path, _value):
        raise config.SecureStoreError("DPAPI unavailable")

    monkeypatch.setattr(config, "save_secret", fail_save)
    settings = TelegramSettings(
        enabled=True,
        allowed_user_ids=[111],
        allowed_chat_ids=[222],
        allowed_tools=["get_local_time"],
        token=TOKEN,
    )
    with pytest.raises(config.SecureStoreError):
        save_settings(settings_path, settings)
    assert not settings_path.exists()


def test_disabling_telegram_deletes_dpapi_token(monkeypatch, tmp_path: Path):
    from hellsaiz_pc_ai.telegram import config

    protected = {}
    monkeypatch.setattr(config, "save_secret", lambda path, value: protected.update({str(path): value}))
    monkeypatch.setattr(config, "delete_secret", lambda path: protected.pop(str(path), None))
    monkeypatch.setattr(config, "load_secret", lambda path: protected.get(str(path), ""))

    path = tmp_path / "telegram.json"
    save_settings(path, TelegramSettings(True, [111], [222], ["get_local_time"], TOKEN))
    save_settings(path, TelegramSettings(False, [111], [222], [], ""))
    assert load_settings(path).token == ""
    assert not protected


def test_worker_does_not_run_poll_without_required_proxy():
    statuses = []
    worker = make_worker(
        network_checker=lambda *_args: type("Health", (), {"ok": False, "latency_ms": 0})(),
        status_callback=statuses.append,
        network_retry_seconds=0,
    )
    worker.stop()
    worker.run()
    assert any("ожидает" in item for item in statuses)



def test_worker_run_polls_and_replies_only_to_an_authorized_safe_command():
    calls = []
    worker_holder = {}

    def api_call(method, payload):
        calls.append((method, payload))
        if method == "getMe":
            return {"ok": True, "result": {"id": 1, "username": "hellsaiz_test_bot"}}
        if method == "getUpdates":
            worker_holder["worker"].stop()
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 10,
                        "message": {
                            "from": {"id": 111},
                            "chat": {"id": 222},
                            "text": "/time",
                        },
                    },
                    {
                        "update_id": 11,
                        "message": {
                            "from": {"id": 999},
                            "chat": {"id": 222},
                            "text": "/time",
                        },
                    },
                ],
            }
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": 2}}
        raise AssertionError(method)

    worker = make_worker(api_call=api_call, require_proxy=False)
    worker_holder["worker"] = worker
    worker.run()

    assert [method for method, _payload in calls] == ["getMe", "getUpdates", "sendMessage"]
    assert calls[-1][1] == {"chat_id": 222, "text": "12:34"}


def test_worker_rejects_unsafe_or_unknown_registry_tools():
    worker = make_worker(allowed_tools={"get_local_time", "unsafe_action"})
    assert "безопасности" in worker._execute_safe_tool("unsafe_action").casefold()
    assert "отключена" in worker._execute_safe_tool("get_system_info").casefold()


def test_telegram_token_is_saved_separately_from_json_and_loaded(monkeypatch, tmp_path: Path):
    from hellsaiz_pc_ai.telegram import config

    protected = {}

    def fake_save(path, value):
        protected[str(path)] = "dpapi:" + value

    def fake_load(path):
        stored = protected.get(str(path), "")
        return stored.removeprefix("dpapi:")

    def fake_delete(path):
        protected.pop(str(path), None)

    monkeypatch.setattr(config, "save_secret", fake_save)
    monkeypatch.setattr(config, "load_secret", fake_load)
    monkeypatch.setattr(config, "delete_secret", fake_delete)

    settings_path = tmp_path / "telegram.json"
    settings = TelegramSettings(
        enabled=True,
        allowed_user_ids=[111],
        allowed_chat_ids=[222],
        allowed_tools=["get_local_time"],
        token=TOKEN,
    )
    save_settings(settings_path, settings)

    raw_json = settings_path.read_text(encoding="utf-8")
    assert TOKEN not in raw_json
    assert "token" not in raw_json
    assert protected[str(settings_path.with_name("telegram_token.dpapi"))] == "dpapi:" + TOKEN

    restored = load_settings(settings_path)
    assert restored.token == TOKEN
    assert restored.enabled


def test_telegram_token_persistence_failure_does_not_enable_or_write_config(monkeypatch, tmp_path: Path):
    from hellsaiz_pc_ai.telegram import config

    settings_path = tmp_path / "telegram.json"

    def fail_save(_path, _value):
        raise config.SecureStoreError("DPAPI unavailable")

    monkeypatch.setattr(config, "save_secret", fail_save)
    settings = TelegramSettings(
        enabled=True,
        allowed_user_ids=[111],
        allowed_chat_ids=[222],
        allowed_tools=["get_local_time"],
        token=TOKEN,
    )

    with pytest.raises(config.SecureStoreError):
        save_settings(settings_path, settings)

    assert not settings_path.exists()


def test_disabling_telegram_deletes_stale_token(monkeypatch, tmp_path: Path):
    from hellsaiz_pc_ai.telegram import config

    protected = {}
    monkeypatch.setattr(config, "save_secret", lambda path, value: protected.update({str(path): value}))
    monkeypatch.setattr(config, "delete_secret", lambda path: protected.pop(str(path), None))
    monkeypatch.setattr(config, "load_secret", lambda path: protected.get(str(path), ""))

    path = tmp_path / "telegram.json"
    save_settings(
        path,
        TelegramSettings(True, [111], [222], ["get_local_time"], token=TOKEN),
    )
    settings = TelegramSettings(False, [111], [222], [], token="")
    save_settings(path, settings)
    assert load_settings(path).token == ""
    assert not protected


def test_telegram_user_and_chat_id_signs_are_validated(tmp_path: Path):
    path = tmp_path / "telegram.json"
    path.write_text(
        '{"schema_version":1,"enabled":true,"allowed_user_ids":[-1],'
        '"allowed_chat_ids":[2],"allowed_tools":["get_local_time"]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="положительные ID"):
        load_settings(path)

    path.write_text(
        '{"schema_version":1,"enabled":true,"allowed_user_ids":[1],'
        '"allowed_chat_ids":[-2],"allowed_tools":["get_local_time"]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="положительные ID"):
        load_settings(path)
