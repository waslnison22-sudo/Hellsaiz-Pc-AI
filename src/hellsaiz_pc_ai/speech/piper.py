from __future__ import annotations

import subprocess
from pathlib import Path


class SpeechSynthesisError(RuntimeError):
    pass


class PiperSynthesizer:
    """Offline TTS adapter for the Piper CLI and a locally stored voice model."""

    def __init__(self, executable: Path, voice_model: Path, timeout_seconds: int = 120) -> None:
        self.executable = executable
        self.voice_model = voice_model
        self.timeout_seconds = timeout_seconds

    def synthesize(self, text: str, output_file: Path) -> Path:
        text = text.strip()
        if not text:
            raise ValueError("Text for speech synthesis is empty.")
        if len(text) > 5000:
            raise ValueError("Speech synthesis input is limited to 5000 characters.")
        if not self.executable.is_file():
            raise FileNotFoundError(f"Piper executable not found: {self.executable}")
        if not self.voice_model.is_file():
            raise FileNotFoundError(f"Piper voice model not found: {self.voice_model}")
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
        if not output_file.is_file() or output_file.stat().st_size < 44:
            raise SpeechSynthesisError("Piper did not produce a valid WAV file.")
        return output_file
