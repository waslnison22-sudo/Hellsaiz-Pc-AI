import wave
from pathlib import Path

import pytest

from hellsaiz_pc_ai.speech.vosk import VoskTranscriber


def write_wav(path: Path, channels: int = 1):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 1600)
    return path


def test_vosk_rejects_stereo_audio(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    audio = write_wav(tmp_path / "stereo.wav", channels=2)
    with pytest.raises(RuntimeError, match="mono PCM16"):
        VoskTranscriber(model).transcribe(audio)


def test_vosk_model_is_loaded_once_for_multiple_transcriptions(tmp_path, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace

    calls = {"models": 0}

    class FakeModel:
        def __init__(self, model_dir):
            calls["models"] += 1
            self.model_dir = model_dir

    class FakeRecognizer:
        def __init__(self, model, sample_rate):
            self.model = model
            self.sample_rate = sample_rate

        def AcceptWaveform(self, frames):
            return False

        def FinalResult(self):
            return json.dumps({"text": "hello"})

    monkeypatch.setitem(
        sys.modules,
        "vosk",
        SimpleNamespace(Model=FakeModel, KaldiRecognizer=FakeRecognizer),
    )
    model = tmp_path / "model"
    model.mkdir()
    first_audio = write_wav(tmp_path / "first.wav")
    second_audio = write_wav(tmp_path / "second.wav")
    VoskTranscriber.clear_model_cache()

    try:
        assert VoskTranscriber(model).transcribe(first_audio) == "hello"
        assert VoskTranscriber(model).transcribe(second_audio) == "hello"
        assert calls["models"] == 1
    finally:
        VoskTranscriber.clear_model_cache()


def test_vosk_model_load_failure_is_reported(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    class BrokenModel:
        def __init__(self, model_dir):
            raise RuntimeError("bad model format")

    class FakeRecognizer:
        pass

    monkeypatch.setitem(
        sys.modules,
        "vosk",
        SimpleNamespace(Model=BrokenModel, KaldiRecognizer=FakeRecognizer),
    )
    model = tmp_path / "model"
    model.mkdir()
    audio = write_wav(tmp_path / "input.wav")
    VoskTranscriber.clear_model_cache()

    try:
        with pytest.raises(RuntimeError, match="Could not load Vosk model"):
            VoskTranscriber(model).transcribe(audio)
    finally:
        VoskTranscriber.clear_model_cache()
