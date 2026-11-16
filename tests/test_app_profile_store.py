import json
from pathlib import Path

import pytest

from hellsaiz_pc_ai.app.profile_store import save_ai_profile


def test_ai_profile_is_saved_as_utf8_json_atomically(tmp_path: Path):
    path = tmp_path / "ai_profile.json"
    path.write_text('{"previous": true}', encoding="utf-8")

    save_ai_profile(
        path,
        {
            "wake_command_timeout": 8,
            "reply_style": "normal",
            "label": "Хеллсайз",
        },
    )

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["wake_command_timeout"] == 8
    assert saved["reply_style"] == "normal"
    assert saved["label"] == "Хеллсайз"
    assert list(tmp_path.glob(".ai_profile.json.*.tmp")) == []


def test_invalid_ai_profile_does_not_replace_previous_file(tmp_path: Path):
    path = tmp_path / "ai_profile.json"
    previous = '{"valid": true}\n'
    path.write_text(previous, encoding="utf-8")

    with pytest.raises(ValueError, match="подготовить профиль"):
        save_ai_profile(path, {"invalid": object()})

    assert path.read_text(encoding="utf-8") == previous


def test_ai_profile_requires_object():
    with pytest.raises(ValueError, match="JSON-объектом"):
        save_ai_profile(Path("unused.json"), [])
