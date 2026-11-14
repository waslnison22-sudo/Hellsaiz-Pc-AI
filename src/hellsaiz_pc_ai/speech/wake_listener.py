from __future__ import annotations

import json
import queue
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

    Audio is processed from an in-memory queue, never written to disk. After the
    wake alias is detected, the next utterance is captured as a command. An
    utterance that contains both the wake alias and the command is dispatched
    immediately.
    """

    def __init__(
        self,
        model_dir: Path,
        aliases: Sequence[str],
        on_command: Callable[[str], None],
        on_status: Callable[[str], None] | None = None,
        sample_rate: int = 16000,
        command_timeout_seconds: float = 8.0,
        queue_blocks: int = 64,
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
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def listen(self) -> None:
        if not self.model_dir.is_dir():
            raise WakeListenerError(f"Модель Vosk не найдена: {self.model_dir}")
        try:
            import sounddevice as sd
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:
            raise WakeListenerError(
                'Для фоновой активации установи голосовые зависимости: pip install -e ".[voice]"'
            ) from exc

        audio_queue: queue.Queue[bytes] = queue.Queue(maxsize=64)

        def audio_callback(indata, frames, timing, status) -> None:
            if status:
                self.on_status(f"Микрофон: {status}")
            block = bytes(indata)
            try:
                audio_queue.put_nowait(block)
            except queue.Full:
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    audio_queue.put_nowait(block)
                except queue.Full:
                    pass

        try:
            model = Model(str(self.model_dir))
            recognizer = KaldiRecognizer(model, self.sample_rate)
            awaiting_command = False
            command_deadline = 0.0
            self.on_status("Ожидаю обращение «Хеллсайз»…")
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=4000,
                channels=1,
                dtype="int16",
                callback=audio_callback,
            ):
                while not self._stop.is_set():
                    try:
                        block = audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        if awaiting_command and time.monotonic() >= command_deadline:
                            awaiting_command = False
                            recognizer = KaldiRecognizer(model, self.sample_rate)
                            self.on_status("Ожидаю обращение…")
                        continue

                    if not recognizer.AcceptWaveform(block):
                        continue
                    result = json.loads(recognizer.Result())
                    transcript = str(result.get("text") or "").strip()
                    recognizer = KaldiRecognizer(model, self.sample_rate)
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
