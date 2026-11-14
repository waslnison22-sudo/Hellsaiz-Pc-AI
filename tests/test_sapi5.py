import pytest

from hellsaiz_pc_ai.speech.sapi5 import Sapi5Synthesizer


def test_sapi5_rejects_invalid_rate():
    with pytest.raises(ValueError):
        Sapi5Synthesizer(rate=400)


def test_sapi5_rejects_invalid_volume():
    with pytest.raises(ValueError):
        Sapi5Synthesizer(volume=1.1)


class FakeSapiVoice:
    def __init__(self, voice_id, name, languages=()):
        self.id = voice_id
        self.name = name
        self.languages = languages


class FakeSapiEngine:
    def __init__(self, voices):
        self.voices = voices
        self.properties = {}
        self.spoken = []
        self.stopped = False

    def getProperty(self, name):
        if name == "voices":
            return self.voices
        return self.properties.get(name)

    def setProperty(self, name, value):
        self.properties[name] = value

    def say(self, text):
        self.spoken.append(text)

    def runAndWait(self):
        return None

    def stop(self):
        self.stopped = True


def test_sapi5_lists_installed_voices_and_stops_engine(monkeypatch):
    voices = [
        FakeSapiVoice("voice-id-1", "RHVoice Irina", ["ru-RU"]),
        FakeSapiVoice("voice-id-2", "Microsoft David", ["en-US"]),
    ]
    engine = FakeSapiEngine(voices)
    monkeypatch.setattr("hellsaiz_pc_ai.speech.sapi5._is_windows", lambda: True)
    monkeypatch.setattr(
        Sapi5Synthesizer, "_create_engine", staticmethod(lambda: engine)
    )

    result = Sapi5Synthesizer().list_voices()

    assert [(voice.id, voice.name) for voice in result] == [
        ("voice-id-1", "RHVoice Irina"),
        ("voice-id-2", "Microsoft David"),
    ]
    assert engine.stopped is True


def test_sapi5_selects_voice_by_id_and_applies_rate_and_volume(monkeypatch):
    engine = FakeSapiEngine([FakeSapiVoice("rhvoice-irina-id", "RHVoice Irina")])
    monkeypatch.setattr("hellsaiz_pc_ai.speech.sapi5._is_windows", lambda: True)
    monkeypatch.setattr(
        Sapi5Synthesizer, "_create_engine", staticmethod(lambda: engine)
    )

    Sapi5Synthesizer("rhvoice-irina-id", rate=160, volume=0.65).speak("Проверка.")

    assert engine.properties == {
        "voice": "rhvoice-irina-id",
        "rate": 160,
        "volume": 0.65,
    }
    assert engine.spoken == ["Проверка."]
    assert engine.stopped is True


def test_sapi5_reports_missing_selected_voice(monkeypatch):
    engine = FakeSapiEngine([FakeSapiVoice("voice-id", "RHVoice Irina")])
    monkeypatch.setattr("hellsaiz_pc_ai.speech.sapi5._is_windows", lambda: True)
    monkeypatch.setattr(
        Sapi5Synthesizer, "_create_engine", staticmethod(lambda: engine)
    )

    with pytest.raises(RuntimeError, match="не найден"):
        Sapi5Synthesizer("missing voice").speak("Проверка")

    assert engine.stopped is True


def test_sapi5_rejects_non_windows_voice_discovery(monkeypatch):
    monkeypatch.setattr("hellsaiz_pc_ai.speech.sapi5._is_windows", lambda: False)

    with pytest.raises(RuntimeError, match="only on Windows"):
        Sapi5Synthesizer().list_voices()
