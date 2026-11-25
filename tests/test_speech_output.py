import pytest

from hellsaiz_pc_ai.speech.output import SpeechOutputError, SpeechOutputRouter


class FakeSpeaker:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def speak(self, text):
        self.calls.append(text)
        if self.error:
            raise self.error


def test_primary_tts_engine_is_used_when_available():
    primary = FakeSpeaker()
    fallback = FakeSpeaker()
    router = SpeechOutputRouter({"sapi5": primary, "piper": fallback}, "sapi5", "piper")

    result = router.speak("Привет")

    assert result.engine == "sapi5"
    assert result.fallback_used is False
    assert primary.calls == ["Привет"]
    assert fallback.calls == []


def test_tts_fallback_is_used_when_primary_fails():
    primary = FakeSpeaker(RuntimeError("SAPI is unavailable"))
    fallback = FakeSpeaker()
    router = SpeechOutputRouter({"sapi5": primary, "piper": fallback}, "sapi5", "piper")

    result = router.speak("Привет")

    assert result.engine == "piper"
    assert result.fallback_used is True
    assert "SAPI is unavailable" in result.primary_error
    assert fallback.calls == ["Привет"]


def test_missing_primary_can_use_available_fallback():
    fallback = FakeSpeaker()
    router = SpeechOutputRouter({"sapi5": fallback}, "piper", "sapi5")

    result = router.speak("Проверка")

    assert result.engine == "sapi5"
    assert result.fallback_used is True


def test_all_tts_engines_failure_is_reported():
    router = SpeechOutputRouter(
        {"sapi5": FakeSpeaker(RuntimeError("first")), "piper": FakeSpeaker(RuntimeError("second"))},
        "sapi5",
        "piper",
    )

    with pytest.raises(SpeechOutputError, match="локальными движками"):
        router.speak("Текст")


def test_empty_tts_text_is_ignored():
    router = SpeechOutputRouter({"sapi5": FakeSpeaker()}, "sapi5")

    result = router.speak("   ")

    assert result.engine == "sapi5"


def test_local_command_replies_are_not_spoken():
    from hellsaiz_pc_ai.speech.output import should_speak_answer

    # "помощь" is answered by the local command router, not by the AI.
    assert should_speak_answer(True, workflow_trigger=False, local_command=True) is False
    assert should_speak_answer(True, workflow_trigger=True, local_command=False) is False
    assert should_speak_answer(True, workflow_trigger=False, local_command=False) is True
    assert should_speak_answer(False, workflow_trigger=False, local_command=False) is False


def test_barge_in_stop_reaches_every_engine():
    class StoppableSpeaker(FakeSpeaker):
        def __init__(self):
            super().__init__()
            self.stopped = 0

        def stop(self):
            self.stopped += 1

    primary = StoppableSpeaker()
    fallback = StoppableSpeaker()
    router = SpeechOutputRouter({"sapi5": primary, "piper": fallback}, "sapi5", "piper")

    router.stop()

    assert primary.stopped == 1
    assert fallback.stopped == 1
