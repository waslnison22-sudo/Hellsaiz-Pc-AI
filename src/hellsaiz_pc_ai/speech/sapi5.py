from __future__ import annotations

import os
import threading
from dataclasses import dataclass


class SpeechSynthesisError(RuntimeError):
    pass


@dataclass(frozen=True)
class SapiVoice:
    id: str
    name: str
    languages: tuple[str, ...]


def _is_windows() -> bool:
    return os.name == "nt"


class Sapi5Synthesizer:
    """Offline Windows SAPI5 TTS adapter (for example, an installed RHVoice voice)."""

    _lock = threading.RLock()
    _engine_cache: dict[tuple[str, int, float], object] = {}

    def __init__(self, voice_name: str = "Aleksandr", rate: int = 175, volume: float = 0.9) -> None:
        if not 80 <= rate <= 300:
            raise ValueError("Speech rate must be between 80 and 300.")
        if not 0.0 <= volume <= 1.0:
            raise ValueError("Speech volume must be between 0 and 1.")
        self.voice_name = voice_name.strip()
        self.rate = rate
        self.volume = volume

    @staticmethod
    def _create_engine():
        try:
            import pyttsx3
        except ImportError as exc:
            raise SpeechSynthesisError(
                'SAPI5 bridge is not installed. Run: pip install -e ".[voice]"'
            ) from exc
        try:
            return pyttsx3.init(driverName="sapi5")
        except Exception as exc:
            raise SpeechSynthesisError(f"Could not initialize Windows SAPI5: {exc}") from exc

    def list_voices(self) -> list[SapiVoice]:
        if not _is_windows():
            raise SpeechSynthesisError("Windows SAPI5 is available only on Windows.")
        with self._lock:
            engine = self._get_engine()
            voices = []
            for item in engine.getProperty("voices"):
                languages = tuple(
                    str(language) for language in getattr(item, "languages", ()) or ()
                )
                voices.append(SapiVoice(str(item.id), str(item.name), languages))
            return voices

    def _get_engine(self):
        key = (self.voice_name.casefold(), self.rate, self.volume)
        with self._lock:
            engine = self._engine_cache.get(key)
            if engine is not None:
                return engine
            engine = self._create_engine()
            self._engine_cache[key] = engine
            return engine

    def stop(self) -> None:
        """Прервать текущее воспроизведение (безопасно, если ничего не звучит)."""
        with self._lock:
            for engine in self._engine_cache.values():
                try:
                    engine.stop()
                except Exception:
                    pass

    def speak(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if len(text) > 5000:
            raise ValueError("Speech synthesis input is limited to 5000 characters.")
        if not _is_windows():
            raise SpeechSynthesisError("Windows SAPI5 is available only on Windows.")

        with self._lock:
            engine = self._get_engine()
            try:
                voices = list(engine.getProperty("voices"))
                selected = None
                if self.voice_name:
                    needle = self.voice_name.casefold()
                    selected = next(
                        (
                            voice for voice in voices
                            if needle in str(voice.name).casefold()
                            or needle in str(voice.id).casefold()
                        ),
                        None,
                    )
                    if selected is None:
                        available = ", ".join(str(voice.name) for voice in voices) or "нет"
                        raise SpeechSynthesisError(
                            f"Голос «{self.voice_name}» не найден. Доступные голоса: {available}"
                        )
                if selected is not None:
                    engine.setProperty("voice", selected.id)
                engine.setProperty("rate", self.rate)
                engine.setProperty("volume", self.volume)
                engine.say(text)
                engine.runAndWait()
            except SpeechSynthesisError:
                raise
            except Exception as exc:
                raise SpeechSynthesisError(f"SAPI5 speech failed: {exc}") from exc
