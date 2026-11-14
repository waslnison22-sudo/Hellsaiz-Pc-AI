from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path


class SpeechSynthesisError(RuntimeError):
    pass


class PiperSynthesizer:
    """Offline Piper adapter supporting the classic CLI and the Piper Python API.

    Pass (executable, model) for the classic CLI or only (model) for the
    maintained piper-tts Python package used by the 0.1.4 voice library.
    """

    def __init__(
        self,
        executable: Path | None = None,
        voice_model: Path | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        if voice_model is None:
            if executable is None:
                raise ValueError("A Piper voice model path is required.")
            self.executable = None
            self.voice_model = Path(executable)
        else:
            self.executable = Path(executable) if executable is not None else None
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
        if not self.voice_model.is_file():
            raise FileNotFoundError(f"Piper voice model not found: {self.voice_model}")
        if self.executable is not None:
            if not self.executable.is_file():
                raise FileNotFoundError(f"Piper executable not found: {self.executable}")
            output_file.parent.mkdir(parents=True, exist_ok=True)
            command = [
                str(self.executable), "--model", str(self.voice_model),
                "--output_file", str(output_file),
            ]
            try:
                result = subprocess.run(
                    command, input=text, capture_output=True, text=True, encoding="utf-8",
                    errors="replace", timeout=self.timeout_seconds, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise SpeechSynthesisError("Piper synthesis timed out.") from exc
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()[-2000:]
                raise SpeechSynthesisError(f"Piper failed ({result.returncode}): {detail}")
        else:
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
            raise SpeechSynthesisError(
                "Piper audio playback is currently supported on Windows."
            ) from exc
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="hellsaiz-tts-", suffix=".wav", delete=False
            ) as file:
                temporary_path = Path(file.name)
            self.synthesize(text, temporary_path)
            winsound.PlaySound(str(temporary_path), winsound.SND_FILENAME)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
