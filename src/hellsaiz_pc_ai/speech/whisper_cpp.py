from __future__ import annotations

import subprocess
from pathlib import Path


class SpeechRecognitionError(RuntimeError):
    pass


class WhisperCppTranscriber:
    """Offline STT adapter for the whisper.cpp CLI (whisper-cli.exe on Windows)."""

    def __init__(
        self, executable: Path, model: Path, language: str = "ru", timeout_seconds: int = 180
    ) -> None:
        self.executable = executable
        self.model = model
        self.language = language
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio_file: Path) -> str:
        for required in (self.executable, self.model, audio_file):
            if not required.is_file():
                raise FileNotFoundError(f"Required speech file not found: {required}")
        command = [
            str(self.executable), "-m", str(self.model), "-f", str(audio_file),
            "-l", self.language, "-nt",
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=self.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SpeechRecognitionError("Speech recognition timed out.") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-2000:]
            raise SpeechRecognitionError(f"whisper.cpp failed ({result.returncode}): {detail}")
        transcript = result.stdout.strip()
        if not transcript:
            raise SpeechRecognitionError("whisper.cpp returned an empty transcript.")
        return transcript
