"""Config robustness: unreadable files must not stop the app from starting."""

from __future__ import annotations

from pathlib import Path

from hellsaiz_pc_ai.config import LLMSettings, load_settings


def test_broken_toml_falls_back_to_defaults(tmp_path: Path):
    broken = tmp_path / "config.toml"
    broken.write_bytes(b"[app\nname = 'unterminated")

    settings = load_settings(broken)

    assert settings.llm.enabled == LLMSettings().enabled
    assert settings.llm.base_url == LLMSettings().base_url


def test_missing_config_uses_defaults(tmp_path: Path):
    settings = load_settings(tmp_path / "absent.toml")

    assert settings.llm.base_url == LLMSettings().base_url


def test_binary_garbage_falls_back_to_defaults(tmp_path: Path):
    garbage = tmp_path / "config.toml"
    garbage.write_bytes(b"\x00\x01\x02 not toml at all")

    settings = load_settings(garbage)

    assert settings.llm.timeout_seconds == LLMSettings().timeout_seconds
