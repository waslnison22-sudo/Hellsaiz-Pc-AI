from __future__ import annotations

from pathlib import Path

from hellsaiz_pc_ai.speech.stt import SpeechRouter
from hellsaiz_pc_ai.speech.vosk import VoskTranscriber
from hellsaiz_pc_ai.speech.whisper_cpp import WhisperCppTranscriber


SUPPORTED_STT_ENGINES = ("vosk", "whisper.cpp", "none")


class SpeechConfigurationError(ValueError):
    pass


def build_speech_router(
    *,
    primary: str,
    fallback: str | None = None,
    vosk_model_path: Path | None = None,
    whisper_executable: Path | None = None,
    whisper_model: Path | None = None,
) -> SpeechRouter:
    """Build a local-only STT router from installed model paths.

    An optional fallback is only enabled when its required files are supplied.
    A primary provider is never silently replaced by another provider.
    """
    primary = primary.casefold().strip()
    fallback_value = (fallback or "none").casefold().strip() or "none"
    if primary not in SUPPORTED_STT_ENGINES or primary == "none":
        raise SpeechConfigurationError("Выбери основной движок распознавания: Vosk или Whisper.cpp.")
    if fallback_value not in SUPPORTED_STT_ENGINES:
        raise SpeechConfigurationError("Резервный движок должен быть Vosk, Whisper.cpp или отключён.")

    def configured_engine(name: str):
        if name == "vosk":
            if vosk_model_path is None or not str(vosk_model_path).strip():
                raise SpeechConfigurationError("Не указан путь к локальной модели Vosk.")
            return VoskTranscriber(Path(vosk_model_path).expanduser())
        if name == "whisper.cpp":
            if (
                whisper_executable is None
                or whisper_model is None
                or not str(whisper_executable).strip()
                or not str(whisper_model).strip()
            ):
                raise SpeechConfigurationError(
                    "Для Whisper.cpp укажи путь к whisper-cli.exe и GGML-модели."
                )
            return WhisperCppTranscriber(
                Path(whisper_executable).expanduser(),
                Path(whisper_model).expanduser(),
            )
        raise SpeechConfigurationError(f"Неизвестный STT-движок: {name}")

    engines = {primary: configured_engine(primary)}
    active_fallback = None
    if fallback_value != "none" and fallback_value != primary:
        try:
            engines[fallback_value] = configured_engine(fallback_value)
            active_fallback = fallback_value
        except SpeechConfigurationError:
            # An unconfigured fallback is omitted. The primary engine still
            # runs and will return its actual diagnostic if it fails.
            active_fallback = None

    return SpeechRouter(engines, primary, active_fallback)
