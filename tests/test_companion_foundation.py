from __future__ import annotations

import json
from pathlib import Path

import pytest

from hellsaiz_pc_ai.companion import (
    CompanionController,
    CompanionEmotion,
    CompanionMode,
    CompanionSnapshot,
    CompanionViseme,
)
from hellsaiz_pc_ai.companion.model_manifest import load_model_manifest, validate_model_manifest


def test_companion_controller_emits_snapshots_and_unsubscribes():
    controller = CompanionController()
    received = []
    unsubscribe = controller.subscribe(received.append)

    controller.set_mode(CompanionMode.LISTENING)
    controller.set_mode(CompanionMode.THINKING)
    controller.set_emotion(CompanionEmotion.CURIOUS, 0.7)

    assert received[0].mode == CompanionMode.HIDDEN
    assert received[-1].emotion == CompanionEmotion.CURIOUS
    assert received[-1].emotion_weight == 0.7

    unsubscribe()
    previous_count = len(received)
    controller.set_mode(CompanionMode.IDLE)
    assert len(received) == previous_count


def test_companion_speech_visemes_require_speaking_mode():
    controller = CompanionController()

    with pytest.raises(ValueError, match="SPEAKING"):
        controller.set_viseme(CompanionViseme.VOWEL_A, 0.8)

    controller.set_mode(CompanionMode.SPEAKING)
    snapshot = controller.set_viseme(CompanionViseme.VOWEL_A, 0.8)

    assert snapshot.viseme == CompanionViseme.VOWEL_A
    assert snapshot.mouth_weight == 0.8

    idle = controller.set_mode(CompanionMode.IDLE)
    assert idle.viseme == CompanionViseme.SILENCE
    assert idle.mouth_weight == 0.0


def test_companion_controller_validates_animation_ranges():
    with pytest.raises(ValueError):
        CompanionSnapshot(emotion_weight=1.1)
    with pytest.raises(ValueError):
        CompanionSnapshot(gaze_x=1.2)
    with pytest.raises(ValueError):
        CompanionSnapshot(mode=CompanionMode.IDLE, viseme=CompanionViseme.VOWEL_A)


def test_model_manifest_loads_valid_local_model_package(tmp_path: Path):
    (tmp_path / "character.model3.json").write_text("{}", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "model_id": "hellsaiz-demo",
        "display_name": "Hellsaiz demo",
        "format_id": "live2d",
        "renderer_id": "live2d-cubism",
        "entrypoint": "character.model3.json",
    }
    path = tmp_path / "companion.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    info = load_model_manifest(path)

    assert info.model_id == "hellsaiz-demo"
    assert info.format_id == "live2d"
    assert info.renderer_id == "live2d-cubism"


@pytest.mark.parametrize("entrypoint", ["../outside.model3.json", "/outside.model3.json", "C:/outside.json"])
def test_model_manifest_rejects_paths_outside_model_directory(tmp_path: Path, entrypoint: str):
    manifest = {
        "schema_version": 1,
        "model_id": "safe-model",
        "display_name": "Safe model",
        "format_id": "vrm",
        "renderer_id": "vrm-three",
        "entrypoint": entrypoint,
    }
    with pytest.raises(ValueError):
        validate_model_manifest(manifest, tmp_path / "manifest.json")


def test_model_manifest_rejects_unknown_format_and_bad_id(tmp_path: Path):
    manifest = {
        "schema_version": 1,
        "model_id": "../../bad",
        "display_name": "Bad model",
        "format_id": "unknown",
        "renderer_id": "renderer",
        "entrypoint": "model.bin",
    }
    with pytest.raises(ValueError):
        validate_model_manifest(manifest, tmp_path / "manifest.json")
