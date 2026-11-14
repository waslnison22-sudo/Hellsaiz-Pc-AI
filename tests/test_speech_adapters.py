from pathlib import Path
from unittest.mock import Mock

import pytest

from hellsaiz_pc_ai.speech.piper import PiperSynthesizer
from hellsaiz_pc_ai.speech.whisper_cpp import WhisperCppTranscriber


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"test")
    return path


def test_whisper_cpp_invokes_cli_with_local_model(tmp_path, monkeypatch):
    executable = touch(tmp_path / "whisper-cli.exe")
    model = touch(tmp_path / "ggml-small.bin")
    audio = touch(tmp_path / "input.wav")
    completed = Mock(returncode=0, stdout="  Привет, компьютер.  \n", stderr="")
    run = Mock(return_value=completed)
    monkeypatch.setattr("hellsaiz_pc_ai.speech.whisper_cpp.subprocess.run", run)

    result = WhisperCppTranscriber(executable, model).transcribe(audio)

    assert result == "Привет, компьютер."
    args = run.call_args.args[0]
    assert args[:4] == [str(executable), "-m", str(model), "-f"]
    assert "-l" in args and "ru" in args


def test_piper_requires_existing_voice_files(tmp_path):
    synth = PiperSynthesizer(tmp_path / "piper.exe", tmp_path / "voice.onnx")
    with pytest.raises(FileNotFoundError):
        synth.synthesize("Привет", tmp_path / "out.wav")


def test_piper_writes_audio_to_requested_file(tmp_path, monkeypatch):
    executable = touch(tmp_path / "piper.exe")
    model = touch(tmp_path / "voice.onnx")
    output = tmp_path / "out.wav"

    def fake_run(command, **kwargs):
        output.write_bytes(b"RIFF" + b"0" * 48)
        return Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("hellsaiz_pc_ai.speech.piper.subprocess.run", fake_run)
    result = PiperSynthesizer(executable, model).synthesize("Тест", output)
    assert result == output


def test_piper_python_voice_is_cached_across_synthesizer_instances(tmp_path, monkeypatch):
    import sys
    import wave
    from types import SimpleNamespace

    model = touch(tmp_path / "voice.onnx")
    output_one = tmp_path / "one.wav"
    output_two = tmp_path / "two.wav"
    loads = {"count": 0}

    class FakeVoice:
        def synthesize_wav(self, text, wav_file):
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\0\0" * 400)

    class FakePiperVoice:
        @staticmethod
        def load(path):
            loads["count"] += 1
            assert Path(path) == model.resolve()
            return FakeVoice()

    monkeypatch.setitem(
        sys.modules, "piper", SimpleNamespace(PiperVoice=FakePiperVoice)
    )
    PiperSynthesizer.clear_voice_cache()

    try:
        assert PiperSynthesizer(model).synthesize("Первый ответ", output_one) == output_one
        assert PiperSynthesizer(model).synthesize("Второй ответ", output_two) == output_two
        assert loads["count"] == 1
        with wave.open(str(output_one), "rb") as audio:
            assert audio.getframerate() == 22050
            assert audio.getnframes() == 400
    finally:
        PiperSynthesizer.clear_voice_cache()


def test_piper_voice_cache_is_bounded(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    models = [touch(tmp_path / f"voice-{index}.onnx") for index in range(3)]
    loads = []

    class FakePiperVoice:
        @staticmethod
        def load(path):
            loads.append(path)
            return object()

    monkeypatch.setitem(
        sys.modules, "piper", SimpleNamespace(PiperVoice=FakePiperVoice)
    )
    PiperSynthesizer.clear_voice_cache()

    try:
        for model in models:
            PiperSynthesizer(model)._load_voice()
        assert len(PiperSynthesizer._voice_cache) == 2
    finally:
        PiperSynthesizer.clear_voice_cache()
