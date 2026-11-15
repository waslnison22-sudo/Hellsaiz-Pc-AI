from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path


class WakeListenerError(RuntimeError):
    pass


def extract_wake_command(
    transcript: str, aliases: Sequence[str]
) -> tuple[bool, str]:
    """Return whether an utterance starts with a configured wake alias and its tail."""
    original = transcript.strip()
    if not original:
        return False, ""
    for alias in sorted(
        (item.strip() for item in aliases if item and item.strip()),
        key=len,
        reverse=True,
    ):
        pattern = re.compile(
            r"^\s*" + re.escape(alias) + r"(?=$|[\s,!?;:.])",
            re.IGNORECASE,
        )
        match = pattern.match(original)
        if match is not None:
            return True, original[match.end():].strip(" \t\r\n,!?;:.—-")
    return False, original


class WakeWordListener:
    """Explicitly enabled, local Vosk wake-word listener.

    Blocking RawInputStream reads keep recognition work out of PortAudio's
    real-time callback. Audio stays in memory and is never written to disk.
    After the wake alias is detected, the next utterance is captured as a
    command. A single utterance containing both is dispatched immediately.
    """

    def __init__(
        self,
        model_dir: Path,
        aliases: Sequence[str],
        on_command: Callable[[str], None],
        on_status: Callable[[str], None] | None = None,
        sample_rate: int = 16000,
        command_timeout_seconds: float = 8.0,
        device: str | int | None = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.aliases = tuple(alias.strip() for alias in aliases if alias and alias.strip())
        if not self.aliases:
            raise ValueError("At least one wake alias is required.")
        if not 8000 <= sample_rate <= 48000:
            raise ValueError("Microphone sample rate must be between 8000 and 48000 Hz.")
        if not 1.0 <= command_timeout_seconds <= 20.0:
            raise ValueError("Wake command timeout must be between 1 and 20 seconds.")
        self.on_command = on_command
        self.on_status = on_status or (lambda _: None)
        self.sample_rate = sample_rate
        self.command_timeout_seconds = command_timeout_seconds
        self.device = device
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def listen(self) -> None:
        if not self.model_dir.is_dir():
            raise WakeListenerError(f"Модель Vosk не найдена: {self.model_dir}")
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model
            from hellsaiz_pc_ai.speech.vosk import VoskTranscriber
        except ImportError as exc:
            raise WakeListenerError(
                'Для фоновой активации установи голосовые зависимости: pip install -e ".[voice]"'
            ) from exc

        try:
            from hellsaiz_pc_ai.speech.capture import resolve_input_sample_rate

            selected_device = self.device
            sample_rate = resolve_input_sample_rate(selected_device, self.sample_rate)
            if isinstance(selected_device, str):
                from hellsaiz_pc_ai.speech.capture import resolve_input_device

                selected_device = resolve_input_device(selected_device)
            model = VoskTranscriber._load_model(self.model_dir, Model)
            recognizer = KaldiRecognizer(model, sample_rate)
            awaiting_command = False
            command_deadline = 0.0
            self.on_status("Ожидаю обращение «Хеллсайз»…")
            read_frames = 4000
            with sd.RawInputStream(
                samplerate=sample_rate,
                blocksize=read_frames,
                channels=1,
                dtype="int16",
                device=selected_device,
            ) as stream:
                while not self._stop.is_set():
                    block, overflowed = stream.read(read_frames)
                    if self._stop.is_set():
                        break
                    if overflowed:
                        self.on_status(
                            "Микрофон: входной аудиобуфер переполнился; часть сигнала могла потеряться. "
                            "Уменьши нагрузку на компьютер или проверь устройство."
                        )
                    if not recognizer.AcceptWaveform(block):
                        continue
                    result = json.loads(recognizer.Result())
                    transcript = str(result.get("text") or "").strip()
                    recognizer = KaldiRecognizer(model, sample_rate)
                    if not transcript:
                        continue

                    if awaiting_command:
                        awaiting_command = False
                        command_deadline = 0.0
                        self.on_status("Команда распознана.")
                        self.on_command(transcript)
                        self.on_status("Ожидаю обращение…")
                        continue

                    matched, command = extract_wake_command(transcript, self.aliases)
                    if not matched:
                        continue
                    if command:
                        self.on_status("Обращение распознано. Выполняю команду…")
                        self.on_command(command)
                        self.on_status("Ожидаю обращение…")
                    else:
                        awaiting_command = True
                        command_deadline = time.monotonic() + self.command_timeout_seconds
                        self.on_status("Слушаю команду…")
        except WakeListenerError:
            raise
        except Exception as exc:
            raise WakeListenerError(f"Не удалось запустить фоновое прослушивание: {exc}") from exc
        finally:
            self.on_status("Фоновое прослушивание выключено.")
