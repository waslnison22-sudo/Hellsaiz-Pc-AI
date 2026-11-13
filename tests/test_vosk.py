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
