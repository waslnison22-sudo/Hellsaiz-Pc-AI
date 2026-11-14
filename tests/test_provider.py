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
