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
        """[assistant]
wake_aliases = ["Хелл", "Hellsaiz"]

[windows.allowed_apps]
steam = ["C:/Steam/steam.exe"]

[windows.app_aliases]
steam = ["стим", "игровой клиент"]
""",
        encoding="utf-8",
    )

    settings = load_settings(path)

    assert settings.wake_aliases == ("Хелл", "Hellsaiz")
    assert settings.app_aliases["steam"] == ("стим", "игровой клиент")


def test_app_aliases_must_reference_allowlisted_apps(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """[windows.app_aliases]
steam = ["стим"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allowlist"):
        load_settings(path)


def test_app_alias_collisions_fail_closed(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """[windows.allowed_apps]
steam = ["steam.exe"]
cs2 = ["cs2.exe"]

[windows.app_aliases]
steam = ["игра"]
cs2 = ["игра"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ambiguous"):
        load_settings(path)



def test_app_alias_cannot_shadow_another_canonical_app_id(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        """[windows.allowed_apps]
steam = ["steam.exe"]
cs2 = ["cs2.exe"]

[windows.app_aliases]
steam = ["cs2"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ambiguous"):
        load_settings(path)



@pytest.mark.parametrize(
    "config_text",
    [
        '[security]\nallow_remote_llm = "false"\n',
        '[llm]\nenabled = "false"\n',
        '[speech]\nauto_speak = "false"\n',
    ],
)
def test_boolean_settings_reject_string_values(tmp_path: Path, config_text: str):
    path = tmp_path / "config.toml"
    path.write_text(config_text, encoding="utf-8")
    with pytest.raises(ValueError, match="must be true or false"):
        load_settings(path)


@pytest.mark.parametrize("timeout", [0, -1, 601])
def test_llm_timeout_is_bounded(tmp_path: Path, timeout: int):
    path = tmp_path / "config.toml"
    path.write_text(f"[llm]\ntimeout_seconds = {timeout}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="timeout_seconds"):
        load_settings(path)
