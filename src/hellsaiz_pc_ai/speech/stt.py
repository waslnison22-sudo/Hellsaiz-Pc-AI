from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class Transcriber(Protocol):
    """Common contract for offline speech-to-text engines."""

    def transcribe(self, audio_file: Path) -> str: ...


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    engine: str
    fallback_used: bool = False
    fallback_reason: str | None = None


class SpeechProviderError(RuntimeError):
    """Raised when every configured local speech engine fails."""


class SpeechRouter:
    """Select a local STT engine and optionally fall back to another local engine.

    Fallback is limited to recognition failures. A missing primary model or
    executable is treated as an unavailable engine and can fall back safely.
    Audio is never uploaded or persisted by this router.
    """

    def __init__(
        self,
        engines: dict[str, Transcriber],
        primary: str,
        fallback: str | None = None,
    ) -> None:
        normalized = {name.casefold().strip(): engine for name, engine in engines.items()}
        if not normalized or any(not name for name in normalized):
            raise ValueError("At least one named speech engine is required.")
        self.engines = normalized
        self.primary = primary.casefold().strip()
        self.fallback = fallback.casefold().strip() if fallback else None
        if self.primary not in normalized:
            raise ValueError(f"Primary speech engine is not configured: {primary}")
        if self.fallback is not None and self.fallback not in normalized:
            raise ValueError(f"Fallback speech engine is not configured: {fallback}")
        if self.fallback == self.primary:
            raise ValueError("Primary and fallback speech engines must be different.")

    def transcribe(self, audio_file: Path) -> TranscriptionResult:
        primary_engine = self.engines[self.primary]
        try:
            text = self._run(primary_engine, audio_file)
            return TranscriptionResult(text=text, engine=self.primary)
        except Exception as primary_error:
            if self.fallback is None:
                raise SpeechProviderError(
                    f"Локальное распознавание ({self.primary}) не выполнено: {primary_error}"
                ) from primary_error

            try:
                text = self._run(self.engines[self.fallback], audio_file)
            except Exception as fallback_error:
                raise SpeechProviderError(
                    "Не удалось распознать речь ни основным движком "
                    f"{self.primary}, ни резервным {self.fallback}. "
                    f"Основная ошибка: {primary_error}. Резервная ошибка: {fallback_error}"
                ) from fallback_error

            return TranscriptionResult(
                text=text,
                engine=self.fallback,
                fallback_used=True,
                fallback_reason=f"{self.primary}: {primary_error}",
            )

    @staticmethod
    def _run(engine: Transcriber, audio_file: Path) -> str:
        text = engine.transcribe(audio_file)
        if not isinstance(text, str) or not text.strip():
            raise SpeechProviderError("Распознаватель вернул пустой текст.")
        return " ".join(text.split())
