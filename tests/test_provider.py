import pytest

from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider


def test_remote_endpoint_is_blocked_by_default():
    with pytest.raises(ValueError, match="Remote LLM endpoints are blocked"):
        OpenAICompatibleProvider("https://example.com/v1", "model")


def test_local_endpoint_is_allowed():
    provider = OpenAICompatibleProvider("http://127.0.0.1:8080/v1", "model")
    assert provider.model == "model"


def test_remote_http_endpoint_is_blocked_even_when_opted_in():
    with pytest.raises(ValueError, match="must use HTTPS"):
        OpenAICompatibleProvider("http://example.com/v1", "model", allow_remote=True)


def test_remote_https_endpoint_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="Remote LLM endpoints are blocked"):
        OpenAICompatibleProvider("https://example.com/v1", "model")


def test_remote_https_endpoint_is_allowed_with_explicit_opt_in():
    provider = OpenAICompatibleProvider(
        "https://example.com/v1", "model", allow_remote=True
    )
    assert provider.base_url == "https://example.com/v1"

@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@example.com/v1",
        "https://example.com/v1?token=secret",
        "ftp://example.com/v1",
    ],
)


def test_endpoint_rejects_unsafe_url_components(url: str):
    with pytest.raises(ValueError, match="valid HTTP"):
        OpenAICompatibleProvider(url, "model", allow_remote=True)


def test_llm_timeout_must_be_bounded():
    with pytest.raises(ValueError, match="timeout"):
        OpenAICompatibleProvider("http://127.0.0.1:1234/v1", "model", timeout_seconds=0)


def test_openai_compatible_provider_discovers_models_and_health(monkeypatch):
    from hellsaiz_pc_ai.providers import openai_compatible

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"data":[{"id":"qwen3"},{"id":"llama3.2"}]}'

    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(openai_compatible, "urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider("http://127.0.0.1:1234/v1", "qwen3")

    assert provider.list_models() == ["qwen3", "llama3.2"]
    health = provider.health_check()
    assert health["model_available"]
    assert health["capabilities"]["chat_completions"]
    assert len(requests) == 2
    assert requests[0][0].full_url == "http://127.0.0.1:1234/v1/models"
