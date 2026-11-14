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
