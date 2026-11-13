from __future__ import annotations

import json
import wave
from pathlib import Path


class VoskRecognitionError(RuntimeError):
    pass


class VoskTranscriber:
    """Offline CPU speech recognition for mono PCM16 WAV files."""

    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir

    def transcribe(self, audio_file: Path) -> str:
        if not self.model_dir.is_dir():
            raise FileNotFoundError(f"Vosk model directory not found: {self.model_dir}")
        if not audio_file.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        try:
            from vosk import KaldiRecognizer, Model
        except ImportError as exc:
            raise VoskRecognitionError(
                'Vosk is not installed. Run: pip install -e ".[voice]"'
            ) from exc

        try:
            with wave.open(str(audio_file), "rb") as audio:
                if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                    raise VoskRecognitionError("Audio must be mono PCM16 WAV.")
                sample_rate = audio.getframerate()
                model = Model(str(self.model_dir))
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
