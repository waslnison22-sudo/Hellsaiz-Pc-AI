from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = 1
SUPPORTED_PROVIDERS = {"lm-studio", "ollama", "llama.cpp", "custom", "gigachat", "deepseek"}
DEFAULT_PROFILE_NAME = "LM Studio"


def _profile(
    name: str,
    provider: str,
    base_url: str,
    model: str,
    enabled: bool = False,
    cloud_notice_shown: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "enabled": enabled,
        "cloud_notice_shown": bool(cloud_notice_shown),
    }


def default_profile_store(
    *,
    base_url: str = "http://127.0.0.1:1234/v1",
    model: str = "local-model",
    enabled: bool = False,
    provider: str = "lm-studio",
) -> dict[str, Any]:
    selected = _profile(DEFAULT_PROFILE_NAME, provider, base_url, model, enabled)
    return {
        "schema_version": SCHEMA_VERSION,
        "active_profile": DEFAULT_PROFILE_NAME,
        "profiles": [
            selected,
            _profile("Ollama", "ollama", "http://127.0.0.1:11434/v1", "llama3.2"),
            _profile(
                "DeepSeek (локальный)",
                "deepseek",
                "http://127.0.0.1:8000/v1",
                "deepseek-chat",
            ),
            _profile(
                "DeepSeek (облако)",
                "deepseek",
                "https://api.deepseek.com",
                "deepseek-chat",
            ),
        ],
    }


def validate_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Профиль AI должен быть объектом.")
    name = value.get("name")
    provider = value.get("provider", "custom")
    base_url = value.get("base_url")
    model = value.get("model")
    enabled = value.get("enabled", False)
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 48:
        raise ValueError("Название AI-профиля должно содержать от 1 до 48 символов.")
    if any(ord(character) < 32 or ord(character) == 127 for character in name.strip()):
        raise ValueError("Название AI-профиля содержит недопустимые символы.")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Неизвестный тип AI-провайдера: {provider}.")
    if not isinstance(base_url, str) or not 1 <= len(base_url.strip()) <= 512:
        raise ValueError("Адрес AI-сервера должен содержать от 1 до 512 символов.")
    parsed = urlparse(base_url.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Адрес AI-сервера должен быть корректным HTTP(S) URL без логина и пароля.")
    if not isinstance(model, str) or not 1 <= len(model.strip()) <= 128:
        raise ValueError("Имя модели должно содержать от 1 до 128 символов.")
    if not isinstance(enabled, bool):
        raise ValueError("Флаг enabled должен быть логическим значением.")
    cloud_notice_shown = value.get("cloud_notice_shown", False)
    if not isinstance(cloud_notice_shown, bool):
        raise ValueError("Флаг cloud_notice_shown должен быть логическим значением.")
    return _profile(
        name.strip(),
        provider,
        base_url.strip(),
        model.strip(),
        enabled,
        cloud_notice_shown,
    )


def load_profile_store(
    path: Path,
    *,
    legacy_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load named AI profiles, or create a backward-compatible store from legacy settings."""
    if not path.is_file():
        legacy = legacy_profile or {}
        provider = str(legacy.get("provider") or "lm-studio")
        if provider not in SUPPORTED_PROVIDERS:
            provider = "custom"
        base_url = str(legacy.get("base_url") or "http://127.0.0.1:1234/v1")
        model = str(legacy.get("model") or "local-model")
        enabled = legacy.get("enabled", False)
        if not isinstance(enabled, bool):
            enabled = False
        return default_profile_store(
            base_url=base_url,
            model=model,
            enabled=enabled,
            provider=provider,
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Не удалось прочитать библиотеку AI-профилей: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Библиотека AI-профилей имеет неподдерживаемую схему.")
    entries = raw.get("profiles")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
        raise ValueError("Библиотека должна содержать от 1 до 32 AI-профилей.")
    profiles = [validate_profile(item) for item in entries]
    names = [item["name"].casefold() for item in profiles]
    if len(set(names)) != len(names):
        raise ValueError("Названия AI-профилей должны быть уникальными.")
    active = raw.get("active_profile")
    if not isinstance(active, str) or active.casefold() not in set(names):
        raise ValueError("Активный AI-профиль отсутствует в библиотеке.")
    canonical_active = next(item["name"] for item in profiles if item["name"].casefold() == active.casefold())
    return {
        "schema_version": SCHEMA_VERSION,
        "active_profile": canonical_active,
        "profiles": profiles,
    }


def save_profile_store(path: Path, store: dict[str, Any]) -> None:
    """Validate and atomically persist the complete user-owned profile library."""
    normalized = load_store_from_value(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_store_from_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Библиотека AI-профилей имеет неподдерживаемую схему.")
    entries = value.get("profiles")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
        raise ValueError("Библиотека должна содержать от 1 до 32 AI-профилей.")
    profiles = [validate_profile(item) for item in entries]
    names = [item["name"].casefold() for item in profiles]
    if len(set(names)) != len(names):
        raise ValueError("Названия AI-профилей должны быть уникальными.")
    active = value.get("active_profile")
    if not isinstance(active, str):
        raise ValueError("Активный AI-профиль не выбран.")
    selected = next((item["name"] for item in profiles if item["name"].casefold() == active.casefold()), None)
    if selected is None:
        raise ValueError("Активный AI-профиль отсутствует в библиотеке.")
    return {
        "schema_version": SCHEMA_VERSION,
        "active_profile": selected,
        "profiles": profiles,
    }


def upsert_profile(
    store: dict[str, Any],
    profile: dict[str, Any],
    *,
    activate: bool = True,
) -> dict[str, Any]:
    normalized_store = load_store_from_value(store)
    normalized_profile = validate_profile(profile)
    profiles = list(normalized_store["profiles"])
    existing_index = next(
        (i for i, item in enumerate(profiles) if item["name"].casefold() == normalized_profile["name"].casefold()),
        None,
    )
    if existing_index is None:
        if len(profiles) >= 32:
            raise ValueError("Достигнут предел в 32 AI-профиля.")
        profiles.append(normalized_profile)
    else:
        profiles[existing_index] = normalized_profile
    active = normalized_profile["name"] if activate else normalized_store["active_profile"]
    return load_store_from_value({
        "schema_version": SCHEMA_VERSION,
        "active_profile": active,
        "profiles": profiles,
    })


def activate_profile(store: dict[str, Any], name: str) -> dict[str, Any]:
    normalized = load_store_from_value(store)
    selected = next(
        (item["name"] for item in normalized["profiles"] if item["name"].casefold() == name.casefold()),
        None,
    )
    if selected is None:
        raise ValueError(f"AI-профиль «{name}» не найден.")
    normalized["active_profile"] = selected
    return normalized


def active_profile(store: dict[str, Any]) -> dict[str, Any]:
    normalized = load_store_from_value(store)
    return next(
        item.copy()
        for item in normalized["profiles"]
        if item["name"] == normalized["active_profile"]
    )


def provider_credential_path(user_data_root: Path, profile_name: str) -> Path:
    """Return a stable opaque path; raw profile names are never used as filenames."""
    normalized = profile_name.casefold().strip().encode("utf-8")
    digest = hashlib.sha256(normalized).hexdigest()[:24]
    return Path(user_data_root) / "provider_credentials" / f"{digest}.dpapi"
