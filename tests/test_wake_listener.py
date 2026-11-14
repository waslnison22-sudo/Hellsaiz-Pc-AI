import pytest

from hellsaiz_pc_ai.speech.wake_listener import WakeWordListener, extract_wake_command


@pytest.mark.parametrize(
    "text, aliases, expected",
    [
        ("Хеллсайз, открой блокнот", ("Хелл", "Хеллсайз"), (True, "открой блокнот")),
        ("  hellsaiz запусти калькулятор ", ("Hellsaiz",), (True, "запусти калькулятор")),
        ("Хеллсайз", ("Хеллсайз",), (True, "")),
        ("Хелл, поставь громкость 30", ("Хелл",), (True, "поставь громкость 30")),
        ("Открой сайт про Хеллсайз", ("Хеллсайз",), (False, "Открой сайт про Хеллсайз")),
        ("Хеллсайзер открой блокнот", ("Хелл",), (False, "Хеллсайзер открой блокнот")),
        ("", ("Хеллсайз",), (False, "")),
    ],
)
def test_extract_wake_command(text, aliases, expected):
    assert extract_wake_command(text, aliases) == expected


def test_listener_requires_at_least_one_alias(tmp_path):
    with pytest.raises(ValueError, match="wake alias"):
        WakeWordListener(tmp_path, [], lambda _: None)


def test_listener_validates_sample_rate_and_command_timeout(tmp_path):
    with pytest.raises(ValueError, match="sample rate"):
        WakeWordListener(tmp_path, ["Хелл"], lambda _: None, sample_rate=1000)
    with pytest.raises(ValueError, match="timeout"):
        WakeWordListener(
            tmp_path, ["Хелл"], lambda _: None, command_timeout_seconds=60
        )


def test_stop_is_idempotent(tmp_path):
    listener = WakeWordListener(tmp_path, ["Хелл"], lambda _: None)

    listener.stop()
    listener.stop()

    assert listener._stop.is_set()


def test_listener_opens_selected_microphone_device(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    model_dir = tmp_path / "vosk"
    model_dir.mkdir()
    listener_box = {}

    class FakeModel:
        def __init__(self, path):
            self.path = path

    class FakeRecognizer:
        def __init__(self, model, sample_rate):
            self.model = model
            self.sample_rate = sample_rate

    class FakeStream:
        def __init__(self, **kwargs):
            listener_box["kwargs"] = kwargs

        def __enter__(self):
            listener_box["listener"].stop()
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    fake_sounddevice = SimpleNamespace(
        RawInputStream=FakeStream,
        query_devices=lambda device=None, kind=None: {"default_samplerate": 16000},
        check_input_settings=lambda **kwargs: None,
    )
    fake_vosk = SimpleNamespace(Model=FakeModel, KaldiRecognizer=FakeRecognizer)
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)
    monkeypatch.setitem(sys.modules, "vosk", fake_vosk)
    monkeypatch.setattr(
        "hellsaiz_pc_ai.speech.capture.resolve_input_device",
        lambda _name: 7,
    )
    from hellsaiz_pc_ai.speech.vosk import VoskTranscriber

    VoskTranscriber.clear_model_cache()
    listener = WakeWordListener(
        model_dir,
        ["Хелл"],
        lambda _: None,
        device="USB Mic · WASAPI",
    )
    listener_box["listener"] = listener

    try:
        listener.listen()
        assert listener_box["kwargs"]["device"] == 7
        assert len(VoskTranscriber._model_cache) == 1
    finally:
        VoskTranscriber.clear_model_cache()
