import pytest

from hellsaiz_pc_ai.hotkeys import to_pynput_combo


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Ctrl+Alt+H", "<ctrl>+<alt>+h"),
        ("Ctrl+Shift+F12", "<ctrl>+<shift>+<f12>"),
        ("Win+Space", "<cmd>+<space>"),
    ],
)
def test_hotkey_conversion(value, expected):
    assert to_pynput_combo(value) == expected


def test_hotkey_requires_modifier():
    with pytest.raises(ValueError):
        to_pynput_combo("H")


def test_hotkey_rejects_unknown_key():
    with pytest.raises(ValueError):
        to_pynput_combo("Ctrl+Danger")
