from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Synthesizer(Protocol):
    def speak(self, text: str) -> None: ...


@dataclass(frozen=True)
class SpeechOutputResult:
    engine: str
    fallback_used: bool
    primary_error: str | None = None


class SpeechOutputError(RuntimeError):
    pass


class SpeechOutputRouter:
    """Play a spoken response with one explicit local fallback."""

    def __init__(
        self,
        engines: dict[str, Synthesizer],
        primary: str,
        fallback: str | None = None,
    ) -> None:
        self.engines = {name.casefold().strip(): engine for name, engine in engines.items()}
        self.primary = primary.casefold().strip()
        self.fallback = fallback.casefold().strip() if fallback else None
        if not self.engines:
            raise ValueError("At least one local speech synthesizer is required.")
        if self.fallback == self.primary:
            raise ValueError("Primary and fallback TTS engines must be different.")
        if self.primary not in self.engines and (
            self.fallback is None or self.fallback not in self.engines
        ):
            raise ValueError("Neither the selected TTS engine nor its fallback is available.")

    def stop(self) -> None:
        """Прервать текущее воспроизведение на всех движках (barge-in)."""
        for engine in self.engines.values():
            stop = getattr(engine, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass

    def speak(self, text: str) -> SpeechOutputResult:
        if not text.strip():
            return SpeechOutputResult(self.primary, False)
        errors: list[tuple[str, Exception]] = []
        order = [self.primary]
        if self.fallback and self.fallback not in order:
            order.append(self.fallback)
        for index, name in enumerate(order):
            engine = self.engines.get(name)
            if engine is None:
                errors.append((name, RuntimeError("движок не установлен или голос недоступен")))
                continue
            try:
                engine.speak(text)
                return SpeechOutputResult(
                    engine=name,
                    fallback_used=index > 0,
                    primary_error=str(errors[0][1]) if errors else None,
                )
            except Exception as exc:
                errors.append((name, exc))
        details = "; ".join(f"{name}: {error}" for name, error in errors)
        raise SpeechOutputError(f"Не удалось озвучить ответ локальными движками: {details}") from errors[-1][1]
