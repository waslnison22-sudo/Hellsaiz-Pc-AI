from __future__ import annotations

import sys
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from hellsaiz_pc_ai.speech.capture import (
    AudioCaptureError,
    list_input_devices,
    record_microphone,
    resolve_input_device,
)


class FakeSoundDevice:
    def __init__(self):
        self.record_calls = []
        self.input_devices = [
            {"name": "USB Mic", "max_input_channels": 1, "hostapi": 0, "default_samplerate": 48000},
            {"name": "Speakers", "max_input_channels": 0, "hostapi": 0, "default_samplerate": 48000},
            {"name": "Laptop Mic", "max_input_channels": 2, "hostapi": 1, "default_samplerate": 44100},
        ]

    def query_devices(self):
        return self.input_devices

    def query_hostapis(self):
        return [{"name": "WASAPI"}, {"name": "MME"}]

    def rec(self, *args, **kwargs):
        self.record_calls.append(kwargs)
        return SimpleNamespace(tobytes=lambda: b"\0\0" * 16)

    def wait(self):
        return None


def test_lists_only_devices_with_input_channels(monkeypatch):
    fake = FakeSoundDevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)

    devices = list_input_devices()

    assert [item.name for item in devices] == ["USB Mic", "Laptop Mic"]
    assert devices[0].host_api == "WASAPI"
    assert devices[1].max_input_channels == 2


def test_resolves_saved_device_name_to_current_index(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice())

    assert resolve_input_device("Laptop Mic") == 2
    assert resolve_input_device(None) is None


def test_missing_saved_device_is_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice())

    with pytest.raises(AudioCaptureError, match="не найден"):
        resolve_input_device("Disconnected Mic")


def test_record_microphone_passes_selected_device_to_sounddevice(tmp_path, monkeypatch):
    fake = FakeSoundDevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    output = tmp_path / "captured.wav"

    result = record_microphone(output, duration_seconds=1.0, device="USB Mic")

    assert result == output
    assert fake.record_calls[0]["device"] == 0
    with wave.open(str(output), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getframerate() == 16000


def test_record_microphone_rejects_invalid_sample_rate(tmp_path):
    with pytest.raises(ValueError, match="Sample rate"):
        record_microphone(tmp_path / "bad.wav", sample_rate=1000)
