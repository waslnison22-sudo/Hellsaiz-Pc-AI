from pathlib import Path

import pytest

from hellsaiz_pc_ai.config import load_settings


def test_speech_config_loads_primary_fallback_and_paths(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """[speech]
stt_primary = "whisper.cpp"
stt_fallback = "vosk"
vosk_model_path = "C:/Models/vosk-ru"
whisper_cpp_executable = "C:/Tools/whisper-cli.exe"
whisper_cpp_model = "C:/Models/ggml-small.bin"
recording_seconds = 7
""",
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.speech.stt_primary == "whisper.cpp"
    assert settings.speech.stt_fallback == "vosk"
    assert settings.speech.vosk_model_path == Path("C:/Models/vosk-ru")
    assert settings.speech.whisper_cpp_executable == Path("C:/Tools/whisper-cli.exe")
    assert settings.speech.whisper_cpp_model == Path("C:/Models/ggml-small.bin")
    assert settings.speech.recording_seconds == 7.0


@pytest.mark.parametrize(
    "section",
    [
        'stt_primary = "unknown"',
        'stt_primary = "none"',
        'stt_fallback = "unknown"',
        'stt_primary = "vosk"\nstt_fallback = "vosk"',
        'recording_seconds = 0',
        'recording_seconds = 16',
        'recording_seconds = "5"',
        'whisper_cpp_model = true',
    ],
)
def test_speech_config_rejects_invalid_values(tmp_path: Path, section: str):
    path = tmp_path / "config.toml"
    path.write_text(f"[speech]\n{section}\n", encoding="utf-8")

    with pytest.raises(ValueError):
        load_settings(path)
