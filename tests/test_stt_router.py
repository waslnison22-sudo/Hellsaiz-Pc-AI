from pathlib import Path

import pytest

from hellsaiz_pc_ai.speech.stt import SpeechProviderError, SpeechRouter


class FakeEngine:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def transcribe(self, audio_file: Path) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_primary_engine_is_used_without_fallback(tmp_path):
    audio = tmp_path / "input.wav"
    primary = FakeEngine("  Привет   мир ")
    fallback = FakeEngine("резерв")

    router = SpeechRouter({"vosk": primary, "whisper": fallback}, "vosk", "whisper")
    result = router.transcribe(audio)

    assert result.text == "Привет мир"
    assert result.engine == "vosk"
    assert result.fallback_used is False
    assert fallback.calls == 0


def test_fallback_is_used_after_primary_failure(tmp_path):
    audio = tmp_path / "input.wav"
    primary = FakeEngine(error=RuntimeError("model unavailable"))
    fallback = FakeEngine("Открой блокнот")

    router = SpeechRouter({"vosk": primary, "whisper.cpp": fallback}, "vosk", "whisper.cpp")
    result = router.transcribe(audio)

    assert result.text == "Открой блокнот"
    assert result.engine == "whisper.cpp"
    assert result.fallback_used is True
    assert "model unavailable" in result.fallback_reason
    assert primary.calls == fallback.calls == 1


def test_all_engines_failure_is_reported(tmp_path):
    primary = FakeEngine(error=RuntimeError("primary broke"))
    fallback = FakeEngine(error=RuntimeError("fallback broke"))
    router = SpeechRouter({"a": primary, "b": fallback}, "a", "b")

    with pytest.raises(SpeechProviderError, match="ни основным движком"):
        router.transcribe(tmp_path / "input.wav")


def test_empty_engine_output_is_rejected(tmp_path):
    router = SpeechRouter({"a": FakeEngine("  ")}, "a")

    with pytest.raises(SpeechProviderError, match="пустой текст"):
        router.transcribe(tmp_path / "input.wav")


@pytest.mark.parametrize(
    "engines, primary, fallback",
    [
        ({}, "vosk", None),
        ({"vosk": FakeEngine()}, "missing", None),
        ({"vosk": FakeEngine()}, "vosk", "missing"),
        ({"vosk": FakeEngine()}, "vosk", "vosk"),
    ],
)
def test_invalid_router_configuration_fails_fast(engines, primary, fallback):
    with pytest.raises(ValueError):
        SpeechRouter(engines, primary, fallback)
