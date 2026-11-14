from pathlib import Path

import pytest

from hellsaiz_pc_ai.speech.factory import SpeechConfigurationError, build_speech_router
from hellsaiz_pc_ai.speech.vosk import VoskTranscriber
from hellsaiz_pc_ai.speech.whisper_cpp import WhisperCppTranscriber


def test_builds_vosk_primary_and_whisper_fallback(tmp_path: Path):
    router = build_speech_router(
        primary="vosk",
        fallback="whisper.cpp",
        vosk_model_path=tmp_path / "vosk",
        whisper_executable=tmp_path / "whisper-cli.exe",
        whisper_model=tmp_path / "ggml-small.bin",
    )

    assert isinstance(router.engines["vosk"], VoskTranscriber)
    assert isinstance(router.engines["whisper.cpp"], WhisperCppTranscriber)
    assert router.primary == "vosk"
    assert router.fallback == "whisper.cpp"


def test_unconfigured_optional_fallback_is_disabled(tmp_path: Path):
    router = build_speech_router(
        primary="vosk",
        fallback="whisper.cpp",
        vosk_model_path=tmp_path / "vosk",
    )

    assert router.primary == "vosk"
    assert router.fallback is None
    assert set(router.engines) == {"vosk"}


def test_whisper_primary_requires_both_local_files(tmp_path: Path):
    with pytest.raises(SpeechConfigurationError, match="whisper-cli.exe"):
        build_speech_router(
            primary="whisper.cpp",
            whisper_executable=tmp_path / "whisper-cli.exe",
        )


def test_vosk_primary_requires_a_model_path():
    with pytest.raises(SpeechConfigurationError, match="Vosk"):
        build_speech_router(primary="vosk")


def test_primary_cannot_be_none():
    with pytest.raises(SpeechConfigurationError):
        build_speech_router(primary="none")
