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
