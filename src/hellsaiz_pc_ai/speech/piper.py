from __future__ import annotations

import hashlib
import subprocess
import threading
import wave
from pathlib import Path


class SpeechSynthesisError(RuntimeError):
    pass


class PiperSynthesizer:
    """Offline Piper adapter supporting the classic CLI and the Piper Python API.

    Pass (executable, model) for the classic CLI or only (model) for the
    maintained piper-tts Python package used by the 0.1.4 voice library.
    """

    _voice_cache: dict[Path, object] = {}
    _cache_lock = threading.RLock()
    _max_cached_voices = 2
    _synthesis_cache: dict[tuple[str, str], Path] = {}
    _max_cached_wav = 48
    _cache_dir: Path | None = None

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

    def _load_voice(self):
        if not self.voice_model.is_file():
            raise FileNotFoundError(f"Piper voice model not found: {self.voice_model}")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise SpeechSynthesisError(
                'Piper is not installed. Run: pip install -e ".[voice]"'
            ) from exc
        key = self.voice_model.resolve()
        with self._cache_lock:
            cached = self._voice_cache.get(key)
            if cached is not None:
                return cached
            try:
                voice = PiperVoice.load(str(key))
            except Exception as exc:
                raise SpeechSynthesisError(f"Could not load Piper voice: {exc}") from exc
            if len(self._voice_cache) >= self._max_cached_voices:
                oldest = next(iter(self._voice_cache))
                del self._voice_cache[oldest]
            self._voice_cache[key] = voice
            return voice

    def _wav_cache_path(self, text: str) -> Path:
        key_text = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
        key_model = hashlib.sha256(str(self.voice_model.resolve()).encode("utf-8")).hexdigest()[:12]
        cache_dir = self._cache_dir
        if cache_dir is None:
            cache_dir = self.voice_model.resolve().parent / "piper-tts-cache"
        return cache_dir / f"{key_model}-{key_text}.wav"

    @classmethod
    def _trim_wav_cache(cls) -> None:
        """Держать кэш синтеза в разумных пределах: старые WAV удаляются с диска."""
        entries = sorted(cls._synthesis_cache.items(), key=lambda item: item[1].stat().st_mtime)
        while len(entries) > cls._max_cached_wav:
            _, oldest_path = entries.pop(0)
            cls._synthesis_cache = {k: v for k, v in cls._synthesis_cache.items() if v != oldest_path}
            try:
                oldest_path.unlink(missing_ok=True)
            except OSError:
                pass

    @classmethod
    def clear_voice_cache(cls) -> None:
        """Release cached native Piper/ONNX sessions during orderly shutdown."""
        with cls._cache_lock:
            cls._voice_cache.clear()

    def stop(self) -> None:
        """Прервать воспроизведение WAV (Windows). Безопасно, если ничего не звучит."""
        try:
            import winsound
        except ImportError:
            return
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

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
                with self._cache_lock:
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
        with self._cache_lock:
            cache_key = (
                hashlib.sha256(str(self.voice_model.resolve()).encode("utf-8")).hexdigest()[:12],
                text,
            )
            cached_path = self._synthesis_cache.get(cache_key)
        if cached_path is not None and cached_path.is_file():
            winsound.PlaySound(str(cached_path), winsound.SND_FILENAME)
            return
        cached_wav = self._wav_cache_path(text)
        cached_wav.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.synthesize(text, cached_wav)
            with self._cache_lock:
                self._synthesis_cache[cache_key] = cached_wav
                self._trim_wav_cache()
        except Exception:
            cached_wav.unlink(missing_ok=True)
            raise
        winsound.PlaySound(str(cached_wav), winsound.SND_FILENAME)
