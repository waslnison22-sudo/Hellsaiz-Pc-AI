import json
from pathlib import Path

import pytest

from hellsaiz_pc_ai.speech import voice_library


def test_voice_id_is_validated():
    assert voice_library._voice_parts("ru_RU-denis-medium") == ("ru", "ru_RU", "denis", "medium")
    with pytest.raises(voice_library.VoiceLibraryError):
        voice_library._voice_parts("../../secret")


def test_download_voice_saves_model_config_and_model_card(tmp_path: Path, monkeypatch):
    def fake_download(url: str, destination: Path, max_bytes: int) -> None:
        if url.endswith(".onnx.json"):
            destination.write_text(json.dumps({"espeak": {"voice": "ru"}}), encoding="utf-8")
        elif url.endswith("MODEL_CARD"):
            destination.write_text("# Model card\n* License: CC0\n", encoding="utf-8")
        else:
            destination.write_bytes(b"fake-onnx-model")

    monkeypatch.setattr(voice_library, "_download", fake_download)
    installed = voice_library.download_voice("ru_RU-denis-medium", tmp_path)

    assert installed.model_path.is_file()
    assert Path(f"{installed.model_path}.json").is_file()
    assert installed.license == "CC0"
    models = voice_library.list_installed_voices(tmp_path)
    assert [item.voice_id for item in models] == ["ru_RU-denis-medium"]


def test_remove_voice_deletes_its_files(tmp_path: Path):
    model = tmp_path / "ru_RU-denis-medium.onnx"
    model.write_bytes(b"model")
    Path(f"{model}.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ru_RU-denis-medium.MODEL_CARD").write_text("card", encoding="utf-8")

    assert voice_library.remove_voice("ru_RU-denis-medium", tmp_path)
    assert not model.exists()
