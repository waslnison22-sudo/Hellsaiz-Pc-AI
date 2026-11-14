from __future__ import annotations

import json
from pathlib import Path

import pytest

from hellsaiz_pc_ai.provider_profiles import (
    active_profile,
    activate_profile,
    default_profile_store,
    load_profile_store,
    save_profile_store,
    upsert_profile,
    validate_profile,
)


def test_legacy_settings_migrate_into_named_profile_store(tmp_path: Path):
    store = load_profile_store(
        tmp_path / "provider_profiles.json",
        legacy_profile={
            "provider": "ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "qwen2.5",
            "enabled": True,
        },
    )

    current = active_profile(store)
    assert current["name"] == "LM Studio"
    assert current["provider"] == "ollama"
    assert current["model"] == "qwen2.5"
    assert current["enabled"] is True


def test_profiles_can_be_saved_selected_and_reloaded(tmp_path: Path):
    path = tmp_path / "provider_profiles.json"
    store = default_profile_store()
    store = upsert_profile(
        store,
        {
            "name": "llama.cpp dev",
            "provider": "llama.cpp",
            "base_url": "http://127.0.0.1:8080/v1",
            "model": "qwen3",
            "enabled": True,
        },
    )
    save_profile_store(path, store)

    loaded = load_profile_store(path)
    assert loaded["active_profile"] == "llama.cpp dev"
    assert active_profile(loaded)["model"] == "qwen3"

    selected = activate_profile(loaded, "Ollama")
    assert selected["active_profile"] == "Ollama"


def test_duplicate_profile_names_are_rejected_case_insensitively():
    store = default_profile_store()
    with pytest.raises(ValueError, match="уникальными"):
        upsert_profile(
            store,
            {
                "name": "ollama",
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "llama3.2",
            },
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"name": "bad\nname"},
        {"base_url": "file:///etc/passwd"},
        {"base_url": "http://user:password@example.com/v1"},
        {"base_url": "http://127.0.0.1:1234/v1?token=secret"},
        {"model": ""},
        {"provider": "unknown"},
        {"enabled": "true"},
    ],
)
def test_invalid_profile_values_are_rejected(changes):
    profile = {
        "name": "Local",
        "provider": "lm-studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "model": "local-model",
        "enabled": False,
    }
    profile.update(changes)
    with pytest.raises(ValueError):
        validate_profile(profile)


def test_corrupted_profile_store_is_rejected(tmp_path: Path):
    path = tmp_path / "provider_profiles.json"
    path.write_text(json.dumps({"schema_version": 1, "active_profile": "missing", "profiles": []}))
    with pytest.raises(ValueError):
        load_profile_store(path)
