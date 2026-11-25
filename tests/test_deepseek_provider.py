"""Tests for the DeepSeek provider (local dsh endpoint and cloud API)."""

from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from hellsaiz_pc_ai.providers.deepseek import (
    HUMAN_BAD_RESPONSE,
    HUMAN_UNAVAILABLE,
    HUMAN_UNAUTHORIZED,
    DeepSeekError,
    DeepSeekProvider,
)


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size=-1):
        return self.payload if size < 0 else self.payload[:size]


def _ok_payload(text: str = "Привет!") -> bytes:
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": text}}]}).encode()


def _provider(opener, *, mode="local", sleeps=None):
    return DeepSeekProvider(
        mode,
        "http://127.0.0.1:8000/v1" if mode == "local" else "https://api.deepseek.com",
        "test-key" if mode == "cloud" else "",
        opener=opener,
        sleep=sleeps.append if sleeps is not None else (lambda _s: None),
    )


def test_local_completion_returns_message():
    calls = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout, request.get_header("Authorization")))
        return FakeResponse(_ok_payload("Готово"))

    provider = _provider(opener)
    result = provider.complete([{"role": "user", "content": "привет"}], [])

    assert result["message"]["content"] == "Готово"
    assert calls[0][0] == "http://127.0.0.1:8000/v1/chat/completions"
    assert calls[0][1] == 8


def test_transient_failures_are_retried_with_backoff():
    calls = {"count": 0}
    sleeps: list[float] = []

    def opener(request, timeout):
        calls["count"] += 1
        if calls["count"] < 3:
            raise TimeoutError("timed out")
        return FakeResponse(_ok_payload())

    provider = _provider(opener, sleeps=sleeps)
    result = provider.complete([{"role": "user", "content": "привет"}], [])

    assert result["message"]["content"] == "Привет!"
    assert calls["count"] == 3
    assert sleeps == [0.4, 0.8]


def test_exhausted_retries_raise_human_message():
    def opener(request, timeout):
        raise TimeoutError("timed out")

    provider = _provider(opener)

    with pytest.raises(DeepSeekError) as error:
        provider.complete([{"role": "user", "content": "привет"}], [])

    assert str(error.value) == HUMAN_UNAVAILABLE
    assert "TimeoutError" not in str(error.value)


def test_unauthorized_is_not_retried_and_is_human():
    calls = {"count": 0}

    def opener(request, timeout):
        calls["count"] += 1
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    provider = _provider(opener, mode="cloud")

    with pytest.raises(DeepSeekError) as error:
        provider.complete([{"role": "user", "content": "привет"}], [])

    assert str(error.value) == HUMAN_UNAUTHORIZED
    assert calls["count"] == 1


def test_non_json_answer_is_human():
    def opener(request, timeout):
        return FakeResponse(b"<html>gateway error</html>")

    provider = _provider(opener)

    with pytest.raises(DeepSeekError) as error:
        provider.complete([{"role": "user", "content": "привет"}], [])

    assert str(error.value) == HUMAN_BAD_RESPONSE


def test_cloud_mode_requires_https_and_a_key():
    with pytest.raises(ValueError):
        DeepSeekProvider("cloud", "http://api.deepseek.com", "key")
    with pytest.raises(ValueError):
        DeepSeekProvider("cloud", "https://api.deepseek.com", "")
    with pytest.raises(ValueError):
        DeepSeekProvider("local", "https://example.com", "")


def test_llm_failure_fallback_message_hides_the_technical_cause():
    from hellsaiz_pc_ai.core.orchestrator import llm_failure_message

    message = llm_failure_message(DeepSeekError(HUMAN_UNAVAILABLE))

    assert "провайдер" in message
    assert "Локальные" not in message
    assert "DeepSeekError" not in message
