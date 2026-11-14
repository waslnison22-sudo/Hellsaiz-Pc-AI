from __future__ import annotations

import tempfile
import wave
from pathlib import Path


class SpeechSynthesisError(RuntimeError):
    pass


class PiperSynthesizer:
    """Local Piper neural TTS using the maintained Python API."""

    def __init__(self, voice_model: Path, timeout_seconds: int = 120) -> None:
        self.voice_model = Path(voice_model)
        self.timeout_seconds = timeout_seconds
        self._voice = None

    def _load_voice(self):
        if not self.voice_model.is_file():
            raise FileNotFoundError(f"Piper voice model not found: {self.voice_model}")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise SpeechSynthesisError(
                'Piper is not installed. Run: pip install -e ".[voice]"'
            ) from exc
        if self._voice is None:
            try:
                self._voice = PiperVoice.load(str(self.voice_model))
            except Exception as exc:
                raise SpeechSynthesisError(f"Could not load Piper voice: {exc}") from exc
        return self._voice

    def synthesize(self, text: str, output_file: Path) -> Path:
        text = text.strip()
        if not text:
            raise ValueError("Text for speech synthesis is empty.")
        if len(text) > 5000:
            raise ValueError("Speech synthesis input is limited to 5000 characters.")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            voice = self._load_voice()
            with wave.open(str(output_file), "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)
        except (OSError, ValueError):
            raise
        except Exception as exc:
            output_file.unlink(missing_ok=True)
            raise SpeechSynthesisError(f"Piper synthesis failed: {exc}") from exc
        if not output_file.is_file() or output_file.stat().st_size < 44:
            raise SpeechSynthesisError("Piper did not produce a valid WAV file.")
        return output_file

    def speak(self, text: str) -> None:
        try:
            import winsound
        except ImportError as exc:
            raise SpeechSynthesisError("Piper audio playback is currently supported on Windows.") from exc
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="hellsaiz-tts-", suffix=".wav", delete=False) as file:
                temporary_path = Path(file.name)
            self.synthesize(text, temporary_path)
            winsound.PlaySound(str(temporary_path), winsound.SND_FILENAME)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
