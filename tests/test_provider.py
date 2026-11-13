import pytest

from hellsaiz_pc_ai.providers.openai_compatible import OpenAICompatibleProvider


def test_remote_endpoint_is_blocked_by_default():
    with pytest.raises(ValueError, match="Remote LLM endpoints are blocked"):
        OpenAICompatibleProvider("https://example.com/v1", "model")


def test_local_endpoint_is_allowed():
    provider = OpenAICompatibleProvider("http://127.0.0.1:8080/v1", "model")
    assert provider.model == "model"
