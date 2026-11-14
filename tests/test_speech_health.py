from pathlib import Path

from hellsaiz_pc_ai.app.health import collect_speech_health
from hellsaiz_pc_ai.speech.capture import InputDevice


def test_health_reports_missing_vosk_and_optional_fallback(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("hellsaiz_pc_ai.app.health._module_available", lambda name: name == "sounddevice")
    monkeypatch.setattr(
        "hellsaiz_pc_ai.speech.capture.list_input_devices",
        lambda: [InputDevice(0, "USB Mic", "WASAPI", 1, 48000)],
    )
    checks = collect_speech_health(
        stt_primary="vosk",
        stt_fallback="whisper.cpp",
        vosk_model_path=tmp_path / "missing-vosk",
        whisper_executable=tmp_path / "whisper-cli.exe",
        whisper_model=tmp_path / "ggml.bin",
        tts_engine="sapi5",
        piper_model_path=None,
        is_windows=False,
    )

    by_component = {item.component: item for item in checks}
    assert by_component["Микрофон"].level == "ok"
    assert by_component["STT / vosk"].level == "error"
    assert by_component["STT / Whisper.cpp"].level == "warning"
    assert by_component["TTS / SAPI5"].level == "warning"


def test_health_reports_installed_local_engines(tmp_path: Path, monkeypatch):
    vosk_model = tmp_path / "vosk"
    vosk_model.mkdir()
    whisper_cli = tmp_path / "whisper-cli.exe"
    whisper_cli.write_bytes(b"fake")
    whisper_model = tmp_path / "ggml.bin"
    whisper_model.write_bytes(b"fake")
    piper_model = tmp_path / "voice.onnx"
    piper_model.write_bytes(b"fake")
    monkeypatch.setattr("hellsaiz_pc_ai.app.health._module_available", lambda _name: True)
    monkeypatch.setattr(
        "hellsaiz_pc_ai.speech.capture.list_input_devices",
        lambda: [
            InputDevice(0, "USB Mic", "WASAPI", 1, 48000)
        ],
    )

    checks = collect_speech_health(
        stt_primary="whisper.cpp",
        stt_fallback="vosk",
        vosk_model_path=vosk_model,
        whisper_executable=whisper_cli,
        whisper_model=whisper_model,
        tts_engine="piper",
        piper_model_path=piper_model,
        is_windows=True,
    )

    assert all(item.level == "ok" for item in checks)
