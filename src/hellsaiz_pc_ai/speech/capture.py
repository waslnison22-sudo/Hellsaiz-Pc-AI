from __future__ import annotations

import wave
from pathlib import Path


class AudioCaptureError(RuntimeError):
    pass


def record_microphone(
    output_file: Path, duration_seconds: float = 5.0, sample_rate: int = 16000
) -> Path:
    """Record a short mono PCM16 clip. sounddevice is an optional dependency."""
    if not 0.25 <= duration_seconds <= 30:
        raise ValueError("Recording duration must be between 0.25 and 30 seconds.")
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise AudioCaptureError(
            "Microphone support is not installed. Run: pip install -e ".[voice]""
        ) from exc

    output_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        audio = sd.rec(
            int(duration_seconds * sample_rate), samplerate=sample_rate,
            channels=1, dtype="int16",
        )
        sd.wait()
    except Exception as exc:
        raise AudioCaptureError(f"Could not record from the selected microphone: {exc}") from exc

    with wave.open(str(output_file), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio.tobytes())
    return output_file
