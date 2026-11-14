from pathlib import Path

import pytest

from hellsaiz_pc_ai.config import load_settings


def test_load_toml_config(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[llm]\nbase_url="http://127.0.0.1:9000/v1"\nmodel="test"\n'
        '[windows.allowed_apps]\nnotepad=["notepad.exe"]\n'
        '[windows.allowed_processes]\ndiscord="Discord.exe"\n',
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.llm.model == "test"
    assert settings.allowed_apps["notepad"] == ("notepad.exe",)
    assert settings.allowed_processes["discord"] == "Discord.exe"


def test_invalid_allowlist_fails_closed(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[windows.allowed_apps]\nnotepad="notepad.exe"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_process_allowlist_rejects_paths(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[windows.allowed_processes]\ndanger="../powershell.exe"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_settings(path)



def test_loads_wake_names_and_user_defined_app_aliases(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[assistant]\\nwake_aliases=["Хелл", "Hellsaiz"]\\n'
        '[windows.allowed_apps]\\nsteam=["C:/Steam/steam.exe"]\\n'
        '[windows.app_aliases]\\nsteam=["стим", "игровой клиент"]\\n',
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.wake_aliases == ("Хелл", "Hellsaiz")
    assert settings.app_aliases["steam"] == ("стим", "игровой клиент")


def test_app_aliases_must_reference_allowlisted_apps(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[windows.app_aliases]\\nsteam=["стим"]\\n', encoding="utf-8")

    with pytest.raises(ValueError, match="allowlist"):
        load_settings(path)


def test_app_alias_collisions_fail_closed(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[windows.allowed_apps]\\nsteam=["steam.exe"]\\ncs2=["cs2.exe"]\\n'
        '[windows.app_aliases]\\nsteam=["игра"]\\ncs2=["игра"]\\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ambiguous"):
        load_settings(path)
