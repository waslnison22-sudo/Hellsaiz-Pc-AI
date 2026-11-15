from pathlib import Path

from hellsaiz_pc_ai.speech.output import SpeechOutputRouter
from hellsaiz_pc_ai.speech.piper import PiperSynthesizer
from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer


def test_sapi5_stop_without_engine_is_safe():
    """stop() при пустом кэше движков не должен поднимать ошибку."""
    Sapi5Synthesizer().stop()


def test_piper_stop_without_winsound_is_safe(monkeypatch):
    """stop() молча переживает отсутствие winsound (не-Windows среда)."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winsound":
            raise ImportError("no winsound")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    PiperSynthesizer(voice_model=Path("m.onnx")).stop()


def test_piper_wav_cache_path_is_deterministic_and_scoped():
    synthesizer = PiperSynthesizer(voice_model=Path("some-model.onnx"))
    first = synthesizer._wav_cache_path("привет")
    second = synthesizer._wav_cache_path("привет")
    other = synthesizer._wav_cache_path("другая фраза")
    assert first == second
    assert first != other
    assert first.suffix == ".wav"
    assert "piper-tts-cache" in str(first)


def test_speech_output_router_stop_calls_engine_stop():
    class Engine:
        def __init__(self):
            self.stopped = False

        def speak(self, text):
            return None

        def stop(self):
            self.stopped = True

    engine = Engine()
    router = SpeechOutputRouter({"sapi5": engine}, "sapi5")
    router.stop()
    assert engine.stopped


def test_speech_output_router_stop_tolerates_engines_without_stop():
    class PlainEngine:
        def speak(self, text):
            return None

    router = SpeechOutputRouter({"plain": PlainEngine()}, "plain")
    router.stop()  # не должен поднимать ошибку
