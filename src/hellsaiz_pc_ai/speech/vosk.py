from __future__ import annotations

import json
import threading
import wave
from pathlib import Path


class VoskRecognitionError(RuntimeError):
    pass


class VoskTranscriber:
    """Offline CPU speech recognition for mono PCM16 WAV files.

    The acoustic/language model is cached per absolute model path for the
    process lifetime. Each utterance still gets its own recognizer instance.
    """

    _model_cache: dict[Path, object] = {}
    _model_lock = threading.RLock()
    _max_cached_models = 2

    def __init__(self, model_dir: Path) -> None:
        self.model_dir = Path(model_dir).expanduser()

    @classmethod
    def _load_model(cls, model_dir: Path, model_class: object) -> object:
        key = model_dir.resolve()
        with cls._model_lock:
            cached = cls._model_cache.get(key)
            if cached is not None:
                return cached
            try:
                model = model_class(str(key))
            except Exception as exc:
                raise VoskRecognitionError(f"Could not load Vosk model: {exc}") from exc
            if len(cls._model_cache) >= cls._max_cached_models:
                oldest = next(iter(cls._model_cache))
                del cls._model_cache[oldest]
            cls._model_cache[key] = model
            return model

    @classmethod
    def clear_model_cache(cls) -> None:
        """Release cached native models; primarily useful for orderly shutdown/tests."""
        with cls._model_lock:
            cls._model_cache.clear()

    def transcribe(self, audio_file: Path) -> str:
        if not self.model_dir.is_dir():
            raise FileNotFoundError(f"Vosk model directory not found: {self.model_dir}")
        if not audio_file.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        try:
            with wave.open(str(audio_file), "rb") as audio:
                if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                    raise VoskRecognitionError("Audio must be mono PCM16 WAV.")
                sample_rate = audio.getframerate()
                try:
                    from vosk import KaldiRecognizer, Model
                except ImportError as exc:
                    raise VoskRecognitionError(
                        'Vosk is not installed. Run: pip install -e ".[voice]"'
                    ) from exc

                model = self._load_model(self.model_dir, Model)
                recognizer = KaldiRecognizer(model, sample_rate)
                chunks: list[str] = []
                while True:
                    frames = audio.readframes(4000)
                    if not frames:
                        break
                    if recognizer.AcceptWaveform(frames):
                        phrase = json.loads(recognizer.Result()).get("text", "").strip()
                        if phrase:
                            chunks.append(phrase)
                final_text = json.loads(recognizer.FinalResult()).get("text", "").strip()
                if final_text:
                    chunks.append(final_text)
        except (wave.Error, OSError) as exc:
            raise VoskRecognitionError(f"Could not read WAV audio: {exc}") from exc

        transcript = " ".join(chunks).strip()
        if not transcript:
            raise VoskRecognitionError("No speech was recognized.")
        return transcript
