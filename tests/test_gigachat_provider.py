from __future__ import annotations

import json

import pytest

from hellsaiz_pc_ai.providers.gigachat import GigaChatProvider, GigaChatProviderError


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.payload


def test_native_gigachat_oauth_and_function_call_roundtrip(monkeypatch):
    monkeypatch.setattr("hellsaiz_pc_ai.providers.gigachat.time.time", lambda: 1_000.0)
    requests = []
    responses = [
        {"access_token": "access-token", "expires_at": 2_000},
        {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "functions_state_id": "state-123",
                    "function_call": {
                        "name": "get_weather",
                        "arguments": {"city": "Москва"},
                    },
                }
            }]
        },
        {"choices": [{"message": {"role": "assistant", "content": "В Москве солнечно."}}]},
    ]

    def fake_urlopen(request, timeout):
        requests.append(request)
        assert timeout == 30
        return FakeResponse(responses.pop(0))

    provider = GigaChatProvider(
        "base64-client-credentials",
        "GigaChat-2-Pro",
        timeout_seconds=30,
        urlopen_func=fake_urlopen,
    )
    schemas = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Получить погоду",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    }]
    first = provider.complete(
        [{"role": "system", "content": "Ты локальный помощник."},
         {"role": "user", "content": "Какая погода в Москве?"}],
        schemas,
    )
    assistant_message = first["message"]
    call = assistant_message["tool_calls"][0]
    assert call["function"]["name"] == "get_weather"
    assert json.loads(call["function"]["arguments"]) == {"city": "Москва"}
    assert assistant_message["functions_state_id"] == "state-123"

    final = provider.complete(
        [
            {"role": "system", "content": "Ты локальный помощник."},
            {"role": "user", "content": "Какая погода в Москве?"},
            assistant_message,
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": '{"ok":true,"output":"Солнечно","data":{}}',
            },
        ],
        schemas,
    )
    assert final["message"]["content"] == "В Москве солнечно."

    oauth_request = requests[0]
    assert oauth_request.full_url == provider.OAUTH_URL
    assert oauth_request.get_header("Authorization") == "Basic base64-client-credentials"
    assert oauth_request.get_header("Rquid")
    assert b"scope=GIGACHAT_API_PERS" in oauth_request.data

    first_chat = json.loads(requests[1].data)
    assert first_chat["model"] == "GigaChat-2-Pro"
    assert first_chat["function_call"] == "auto"
    assert first_chat["functions"][0]["name"] == "get_weather"

    second_chat = json.loads(requests[2].data)
    assert second_chat["messages"][-2]["role"] == "assistant"
    assert second_chat["messages"][-2]["functions_state_id"] == "state-123"
    assert second_chat["messages"][-2]["function_call"] == {
        "name": "get_weather",
        "arguments": {"city": "Москва"},
    }
    assert second_chat["messages"][-1]["role"] == "function"
    assert second_chat["messages"][-1]["name"] == "get_weather"


def test_gigachat_rejects_untrusted_endpoint_and_invalid_scope():
    with pytest.raises(ValueError, match="официальный HTTPS"):
        GigaChatProvider(
            "key",
            base_url="https://example.com/v1",
        )
    with pytest.raises(ValueError, match="scope"):
        GigaChatProvider("key", scope="UNSUPPORTED")


def test_gigachat_tool_mapping_rejects_multiple_parallel_calls():
    messages = [{
        "role": "assistant",
        "tool_calls": [
            {"id": "1", "function": {"name": "first", "arguments": "{}"}},
            {"id": "2", "function": {"name": "second", "arguments": "{}"}},
        ],
    }]
    with pytest.raises(GigaChatProviderError, match="один"):
        GigaChatProvider._map_messages(messages)


def test_gigachat_health_check_lists_capabilities(monkeypatch):
    provider = GigaChatProvider("key")
    monkeypatch.setattr(provider, "list_models", lambda: ["GigaChat", "GigaChat-2-Pro"])
    result = provider.health_check()
    assert result["ok"]
    assert result["model_available"]
    assert result["capabilities"]["function_calling"]
